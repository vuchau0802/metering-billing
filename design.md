# Design Document — Usage Metering & Billing Engine

## Problem

Meter a tenant's usage (API calls, AI tokens), enforce plan quotas before allowing billable actions, calculate accurate costs (including AI token pricing rules), and keep subscription state in sync with Stripe via verified, deduplicated webhooks.

## Data model

**`tenants`**
- `id` (PK)
- `email`, `supabase_user_id` (reusing the auth pattern from the widget capstone)
- `plan` (enum: `free` | `pro`)
- `stripe_customer_id` (nullable — set once they interact with Stripe)
- `stripe_subscription_id` (nullable)
- `created_at`

**`plans`** (a config table, not tenant-specific — could also be a plain Python dict, but a table makes limits inspectable/adjustable without a deploy)
- `name` (PK: `free` | `pro`)
- `api_calls_limit` (int, per month)
- `ai_tokens_limit` (int, per month)

**`usage_events`**
- `id` (PK)
- `tenant_id` (FK, indexed)
- `idempotency_key` (TEXT, **unique** — this single constraint is what makes exactly-once metering possible; a duplicate insert attempt fails at the DB level, not just in application logic)
- `usage_type` (enum: `api_call` | `ai_tokens`)
- `quantity` (int — number of calls, or token count)
- `token_breakdown` (JSONB, nullable — for `ai_tokens` events: `{input, cached_input, output, reasoning}`)
- `created_at` (indexed — rollups filter by month)

**`processed_webhook_events`**
- `id` (PK)
- `stripe_event_id` (TEXT, **unique** — the dedup mechanism for webhooks, same idea as the idempotency key above)
- `event_type` (TEXT)
- `processed_at`

## Plans & quotas

| Plan | API calls/month | AI tokens/month |
|------|-----------------|------------------|
| Free | 1,000 | 100,000 |
| Pro  | 50,000 | 5,000,000 |

## Pinned pricing constants (per 1,000 tokens, illustrative — documented in README, not tied to any real provider's exact current rates)

```
INPUT_PRICE_PER_1K = $0.15
CACHED_INPUT_PRICE_PER_1K = $0.075   # half price
OUTPUT_PRICE_PER_1K = $0.60
# reasoning tokens are billed at the OUTPUT rate, not a separate category
```

## The metering API contract & idempotency strategy

```
POST /generate                       (the one dummy billable endpoint)
Headers: Idempotency-Key: <client-generated UUID>
Body: {"tenant_id": ..., "simulated_input_tokens": ..., "simulated_output_tokens": ...}

Flow:
1. Check usage_events for this idempotency_key.
   - If found: return the ORIGINAL stored result. Do nothing else. (This is what
     makes retries safe — a network retry replays the same key and gets the same
     answer, with zero side effects the second time.)
2. If not found: check tenant's current-month usage against their plan's quota.
   - Over quota -> 429 (usage limit) or 402 (plan requires upgrade), never proceed.
3. Record the usage_event (this INSERT is where the UNIQUE constraint on
   idempotency_key provides a final safety net even against a race condition
   between step 1's check and this insert).
4. Return the result, keyed to this idempotency_key so a future retry can find it.

GET /usage/{tenant_id}                -> { used, limit, cost } rollup for the current month

POST /billing/checkout                -> creates a Stripe Checkout session (test mode)
POST /webhooks/stripe                 -> verifies signature, deduplicates by stripe_event_id,
                                          updates tenant plan/status
```

## Layer sketch

```
Route handlers (FastAPI)
    ↓
Service layer: MeterService.record(), QuotaService.check(), CostService.calculate()
    ↓
Repository layer: all SQL, including the UNIQUE constraints that back idempotency/webhook-dedup
    ↓
PostgreSQL (Docker)

Separately: StripeService wraps the Stripe SDK (Checkout session creation, webhook
signature verification) — kept isolated so the core metering/quota logic has zero
Stripe-specific code mixed into it.
```

## Explicit non-goal

**No overage billing, invoicing, or proration in the core.** A request over quota is simply rejected (429/402) — there's no "let it through and bill extra later" logic. These are listed as stretch goals in the brief and are explicitly out of scope for the core build.