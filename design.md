# Design Document — Usage Metering & Billing Engine

## Problem

Meter a tenant's usage (API calls, AI tokens), enforce plan quotas before allowing billable actions, calculate accurate costs (including AI token pricing rules), and keep subscription state in sync with Stripe via verified, deduplicated webhooks.

## Ground rules this design commits to

- **Money is always an integer.** Every monetary amount in this system — the pinned constants, the per-event cost, the rollup total, the API responses — is an integer count of **micro-USD** (1 USD = 1,000,000 micro-USD). No `float` or `Decimal` ever touches a money value. The only division is integer floor division, and it is deterministic (see [Rounding](#rounding)).
- **Stripe is the source of truth for payment state.** The database only ever mirrors Stripe through signature-verified webhooks. Nothing in the metering path writes a tenant's plan or status.

## Data model

Schema is managed as **Alembic migrations** against PostgreSQL (not `CREATE TABLE` at boot).

**`tenants`**
- `id` (PK)
- `email`, `supabase_user_id` (nullable — an auth-provider id; there is no runtime coupling to any other project, the column exists so an external auth system can be attached later)
- `plan` (enum: `free` | `pro`) — **denormalized mirror** of the active subscription's plan, written *only* by the webhook handler. Kept on the tenant row because the quota check runs on every billable request and should not need a join to answer "what is this tenant entitled to?"
- `status` (enum: `active` | `past_due` | `canceled` | `incomplete`) — mirror of Stripe subscription status. `free` tenants sit at `active`.
- `stripe_customer_id` (nullable, unique — set the first time the tenant touches Stripe)
- `api_key_hash` (nullable, unique SHA-256 digest — tenant-scoped routes compare the supplied `X-Tenant-Key` without storing the raw credential)
- `created_at`, `updated_at`

**`plans`** (reference/config table — a table rather than a Python dict so limits are inspectable and adjustable without a deploy)
- `name` (PK: `free` | `pro`)
- `api_calls_limit` (int, per quota window)
- `ai_tokens_limit` (int, per quota window)
- `stripe_price_id` (nullable, unique — the Stripe Price this plan bills to; drives Checkout)

**`subscriptions`** (the ledger — one row per Stripe subscription, kept for history)
- `id` (PK)
- `tenant_id` (FK → `tenants`, indexed)
- `stripe_subscription_id` (TEXT, **unique**)
- `stripe_customer_id` (TEXT, indexed)
- `plan_name` (FK → `plans.name`)
- `status` (enum mirroring Stripe: `active` | `past_due` | `canceled` | `incomplete` | `trialing`)
- `current_period_start`, `current_period_end` (timestamptz)
- `cancel_at_period_end` (bool)
- `created_at`, `updated_at`

**`usage_events`**
- `id` (PK)
- `tenant_id` (FK, indexed)
- `idempotency_key` (TEXT, **unique** — this single constraint is what makes exactly-once metering possible; a duplicate insert fails at the DB level, not merely in application logic)
- `usage_type` (enum: `api_call` | `ai_tokens`)
- `quantity` (int — call count, or total token count)
- `token_breakdown` (JSONB, nullable — only for `ai_tokens` events: `{input, cached_input, output, reasoning}`; **null** for `api_call` events)
- `cost_microusd` (bigint, **not null** — the event's cost frozen at write time, so changing a pinned price later never rewrites historical bills)
- `response_snapshot` (JSONB, **not null** — the exact response body returned the first time, so an idempotent replay is byte-identical)
- `created_at` (indexed — rollups filter by quota window)

**`processed_webhook_events`**
- `id` (PK)
- `stripe_event_id` (TEXT, **unique** — the webhook dedup mechanism, same pattern as the idempotency key above)
- `event_type` (TEXT)
- `processed_at`

## Plans & quotas

| Plan | API calls / window | AI tokens / window |
|------|--------------------|--------------------|
| Free | 1,000 | 100,000 |
| Pro  | 50,000 | 5,000,000 |

**Quota window = UTC calendar month** (`created_at >= first_of_month 00:00:00Z` AND `< first_of_next_month 00:00:00Z`). Deliberately *not* the Stripe billing period: a calendar month keeps the rollup a single indexed range scan, and mid-cycle plan changes are out of core scope. The tradeoff is that an upgrade mid-month does not reset the window — that is a documented simplification, and proration/billing-period-aligned quotas are the stretch goal that revisits it.

## Pinned pricing constants

Integer micro-USD, per 1,000 units. Pinned in config (`config.py`), never hardcoded at a call site.

```
API_CALL_PRICE_PER_1K       =   2_000   # $0.002 per 1,000 API calls
INPUT_PRICE_PER_1K          = 150_000   # $0.15  per 1k input tokens
CACHED_INPUT_PRICE_PER_1K  =  75_000   # $0.075 per 1k cached input tokens (half of input)
OUTPUT_PRICE_PER_1K         = 600_000   # $0.60  per 1k output tokens
# reasoning tokens bill at the OUTPUT rate — there is no separate reasoning price
```

These are illustrative and documented in the README; they are not tied to any real provider's current rates.

### Token categories are not additive

The four categories price differently, so they are costed separately and only then summed:

```
api_call event:
    cost = quantity * API_CALL_PRICE_PER_1K // 1000

ai_tokens event:
    cost =   input_tokens    * INPUT_PRICE_PER_1K         // 1000     # fresh input, full price
           + cached_tokens   * CACHED_INPUT_PRICE_PER_1K  // 1000     # provider cache hit, half price
           + (output_tokens + reasoning_tokens)
                          * OUTPUT_PRICE_PER_1K            // 1000     # reasoning bills as output
```

Two rules keep the token accounting explicit:

1. **`reasoning_tokens` is a sibling of `output_tokens`, not a subset.** Callers provide each token category separately so each category is priced once.
2. **The server derives the total.** Clients do not provide `quantity`; the server calculates it from the four token components. Every component must be a strict, non-negative integer, otherwise the request returns `400 invalid_request`.

### Rounding

All money is integer micro-USD; the only arithmetic is `value * price_per_1k // 1000` (floor). A single event can therefore under-count by at most one micro-USD per priced component. This is intentional: **rounding is applied per event, deterministically**, so recomputing a rollup from the same events always yields the same total. The rollup sums the already-rounded per-event `cost_microusd` values — it never re-rounds.

## API surface & idempotency strategy

```
POST /generate                     the one dummy billable endpoint
  Headers:  X-Tenant-Key: <tenant credential>
            Idempotency-Key: <client-generated UUID>
  Body:     { "tenant_id": int,
              "input_tokens": int, "cached_input_tokens": int,
              "output_tokens": int, "reasoning_tokens": int }
  200:      { "usage_event_id", "idempotency_key", "quantity", "cost_microusd",
              "usage": { "used", "limit", "remaining" } }
            + header `Idempotent-Replay: true` on a replay

GET  /usage/{tenant_id}            requires X-Tenant-Key, then returns
                                      { "window", "usage": { per-type used/limit/remaining },
                                        "cost_microusd" }  rollup for the current window

POST /billing/checkout            requires X-Tenant-Key, then creates a Stripe Checkout session
POST /webhooks/stripe             -> verify signature, dedup by stripe_event_id, sync plan/status
```

### `POST /generate` flow

```
1. Authenticate `X-Tenant-Key` against the requested tenant -> 401 on failure.
2. Validate the body. Non-integer, negative, or all-zero token counts -> 400.
3. Look up usage_events by idempotency_key.
   - Found  -> return the stored response_snapshot verbatim, with `Idempotent-Replay: true`.
               No quota check, no insert, no side effects at all.
   - Missing -> continue.
4. Entitlement check (may this tenant act at all?):
   - tenant.status != 'active' -> 402 payment_required
5. Quota check, per usage type, inside one transaction:
   used = SUM(quantity) for this tenant + type + window
   if used + requested > limit  -> 429 quota_exceeded
   (so used + requested == limit is ALLOWED: a tenant may reach exactly
    its limit and the next request is the one refused)
6. INSERT usage_event (quantity, frozen cost_microusd, response_snapshot).
   The UNIQUE constraint on idempotency_key is the final safety net even
   against a race between step 2's read and this insert: a losing
   transaction catches IntegrityError, re-reads the winning row, and
   returns its response_snapshot — so two concurrent retries still
   produce exactly one event and two identical responses.
7. Commit, return the snapshot with `Idempotent-Replay` absent.
```

### `429` vs `402` — the exact rule

| Code | Meaning | Trigger |
|------|---------|---------|
| `402 payment_required` | The tenant is not entitled to act. No amount of waiting helps. | `tenant.status` is `past_due`, `canceled`, or `incomplete` |
| `429 quota_exceeded` | The tenant is on a valid, paid plan but has spent this window's metered allowance. It resets. | `used + requested > limit` for the usage type |

Every error body is machine-readable and explains itself:

```json
{ "error": { "code": "quota_exceeded",
             "message": "ai tokens quota exceeded for the current UTC month.",
             "usage_type": "ai_tokens",
             "used": 100000, "limit": 100000, "requested": 2500,
             "resets_at": "2026-10-01T00:00:00Z" } }
```

`429` responses also carry a `Retry-After` header (seconds until the window resets) and a `Limit`-style trio of headers. `400` is reserved for malformed input; bad input never produces a `500`.

## Layer sketch

```
Route handlers (FastAPI)          — HTTP only: parse, validate shape, map exceptions -> status codes
    ↓
Service layer                     — MeterService.record(), QuotaService.check(),
                                     CostService.calculate()   <- all the rules in this document
    ↓
Repository layer                  — all SQL, and it owns the UNIQUE constraints that
                                     back idempotency and webhook dedup
    ↓
PostgreSQL (Docker)

StripeService                     — wraps the Stripe SDK (Checkout session creation, webhook
                                     signature verification). Deliberately isolated: the
                                     metering/quota/cost logic contains zero Stripe-specific
                                     code, so all of it is testable with no Stripe account.

Background worker (separate process, not a request-path thread)
    — a periodic reconciliation job: for each tenant with a subscription, compare local
      plan/status against Stripe's view and repair drift. This is the slow/bulk work the
      brief asks to keep off the request path, and it doubles as the safety net for a
      webhook that never arrived. Retries with backoff; failures are logged and alerted.
```

## Explicit non-goal

**No overage billing, invoicing, or proration in the core.** A request over quota is simply rejected (`429`/`402`) — there is no "let it through and bill extra later" logic. These are listed as stretch goals in the brief and are explicitly out of scope for the core build.
