# Evidence

## Phase 2 - Core billing logic

Date verified: 2026-09-27

### Automated verification

Command: `pytest -q`

Result: `31 passed in 0.66s`

The suite covers integer cost calculations, strict request validation,
UTC quota windows, exact quota boundaries, idempotent replay, entitlement
failures, idempotency conflicts, and API error status codes.

### Probe 1 - Idempotent usage tracking

The same `POST /generate` request was sent twice with the same
`Idempotency-Key`.

Observed:

- Both responses returned HTTP 200.
- Both response bodies were identical.
- Both returned `usage_event_id: 1`.
- The second response contained `Idempotent-Replay: true`.
- A direct database count for the idempotency key returned `1`.

Conclusion: retries produce one usage event and one billable charge.

### Probe 2 - Exact quota boundary

A free tenant with zero usage submitted an event containing exactly
100,000 AI tokens. The request was accepted with HTTP 200 and returned:

```json
{
  "used": 100000,
  "limit": 100000,
  "remaining": 0
}
```

A second request for one AI token returned HTTP 429:

```json
{
  "error": {
    "code": "quota_exceeded",
    "usage_type": "ai_tokens",
    "used": 100000,
    "limit": 100000,
    "requested": 1,
    "resets_at": "2026-10-01T00:00:00Z"
  }
}
```

A `Retry-After` header was present, and the usage rollup remained exactly
100,000 after rejection.

Conclusion: reaching the limit exactly is allowed; exceeding it is rejected
without recording additional usage.

### Entitlement probe

A request for seeded tenant `4`, whose status is `past_due`, returned HTTP
402 with:

```json
{
  "error": {
    "code": "payment_required",
    "message": "The tenant is not entitled to perform this action.",
    "tenant_status": "past_due"
  }
}
```

### Usage rollup probe

`GET /usage/1` returned the UTC monthly window, per-type quota usage,
remaining allowance, and total frozen cost in integer micro-USD.

### Pricing verification

For 1,000 input tokens, 500 cached-input tokens, 200 output tokens, and 100
reasoning tokens:

```text
input:            150000 micro-USD
cached input:      37500 micro-USD
output/reasoning: 180000 micro-USD
total:            367500 micro-USD
```

No floating-point money is used.

---

## Phase 3 - Stripe integration

Date verified: 2026-09-29

### Automated verification

Command: `python -m pytest -q`

Result: `37 passed`

The tests cover forged webhook signatures, webhook replay deduplication,
Checkout Free-to-Pro synchronization, subscription lifecycle updates, billing
period persistence, cancellation, and billing redirect endpoints.

### Signature verification probe

A request with a forged `Stripe-Signature` returned HTTP 400:

```json
{
  "error": {
    "code": "invalid_webhook_signature",
    "message": "The Stripe webhook signature is invalid"
  }
}
```

### Replay probe

The same correctly signed event was delivered twice. The first response
reported `duplicate: false`; the second reported `duplicate: true`. A direct
database count showed one processed webhook row.

### Live Stripe Checkout gate

Stripe CLI forwarded real test-mode events to the local API:

```text
customer.subscription.created -> HTTP 200
checkout.session.completed -> HTTP 200
```

Before Checkout, tenant 1 was `free active` with no Stripe customer or
subscription. After verified webhook delivery, the database reported:

```text
tenant: pro active cus_...
subscription: sub_... active
current_period_start: 2026-09-29T04:51:45Z
current_period_end: 2026-10-29T04:51:45Z
```

The Stripe customer ID, subscription ID, active status, and UTC billing period
were persisted. A subsequent Checkout request for tenant 1 returned
`already_subscribed`, preventing a duplicate subscription.

Conclusion: the Phase 3 gate passed. A real Stripe test-mode Checkout upgraded
a Free tenant to Pro through verified, replay-safe webhook processing.

---

## Phase 4 - Cost and finalization

Date verified: 2026-09-30

### Automated verification

Command: `python -m pytest -q`

Result: `40 passed in 0.99s`

The reconciliation tests prove:

- A transient Stripe failure is retried and succeeds.
- Retry delays follow exponential backoff.
- A persistent failure stops after three attempts.
- Persistent failure produces a critical reconciliation alert.
- An incomplete run returns a nonzero process exit code.

### Live background-job probe

Command:

```powershell
python -m app.jobs.reconcile_subscriptions
```

Observed:

```text
Stripe subscription retrieval -> HTTP 200
Reconciled Stripe subscription sub_...
Reconciliation complete: checked=1 succeeded=1 failed=0
```

Database verification after reconciliation:

```text
tenant: pro active
subscription: sub_... active
current_period_start: 2026-09-29T04:51:45Z
current_period_end: 2026-10-29T04:51:45Z
```

Conclusion: subscription reconciliation runs outside the HTTP path, repairs
state through shared synchronization logic, retries transient failures, and
provides an observable failure signal.

### Final acceptance audit

All five published acceptance probes are covered by automated or live
evidence:

1. Repeating one billable request returns the original response and creates
   one usage event.
2. Exact quota usage is accepted; the next unit returns a clear quota error.
3. Stripe test Checkout upgrades a tenant from Free to Pro through verified
   webhooks.
4. A forged webhook returns 400, while a replayed valid event is processed
   once.
5. Cached input and reasoning-token pricing produce the pinned totals, and
   `/usage` returns the same frozen cost.

The final `GET /usage/1` probe returned HTTP 200:

```text
api_calls: used=0 limit=50000 remaining=50000
ai_tokens: used=1800 limit=5000000 remaining=4998200
cost_microusd: 367500
```

Migration verification reported `e5ca33e8ba3d (head)` as both the available
and currently applied Alembic revision. The required submission files are
present, `.env` and PDF files are ignored, and no Stripe secret patterns were
found in tracked files or Git history.

Conclusion: the Phase 4 cost gate and final capstone self-check pass.

---

## Review hardening verification

Date verified: 2026-09-30

- Alembic applied `c91b2f6e4a7d`, adding unique SHA-256 tenant API-key hashes.
- Seed execution completed after migration without overwriting Stripe-managed
  plan, status, customer, or subscription data.
- Tenant-scoped endpoints reject missing or cross-tenant credentials with 401.
- An all-zero token request returns 400 and creates no usage event.
- Webhook duplicate-key races use a savepoint; transaction rollback remains
  owned by the webhook service.
- Stripe's raw request body is still signature-verified, while synchronous
  database processing runs through a normal FastAPI threadpool endpoint.

Command: `python -m pytest -q`

Result: `48 passed, 1 warning in 1.47s`

---

## Overage Billing Evidence

Date verified: 2026-10-01

A Pro tenant with 4,999,900 of 5,000,000 AI tokens used submitted another
200-token request.

Observed:

- Request accepted with HTTP 200.
- Final usage: 5,000,100 tokens.
- Overage quantity: 100 tokens.
- Overage surcharge: 75,000 micro-USD.
- Event total: 105,000 micro-USD.
- Replaying the same idempotency key returned the identical response.
- Exactly one usage event was stored.
- `/usage` reported the same cumulative overage and surcharge.

Command: `python -m pytest -q`

Result: `55 passed in 1.28s`

---

## Usage Alerts Evidence

Date verified: 2026-10-05

### Automated verification

Command: `python -m pytest -q`

Result: `70 passed in 1.81s`

The suite covers exact threshold crossing, crossing both thresholds in one
request, non-duplicate alerts, successful worker delivery, retryable provider
errors, terminal failure, missing tenant email, batch limits, SMTP
configuration validation, email construction, and transport selection.

### Manual threshold and delivery probe

A temporary Free tenant started with zero usage. An 80,000-token request was
accepted and returned `used=80000`, `limit=100000`, and `remaining=20000`.
A second 20,000-token request reached the exact quota and returned
`used=100000` and `remaining=0`.

The alert outbox then contained exactly:

```text
[(80, 'pending', 0), (100, 'pending', 0)]
```

Running the delivery worker produced:

```text
USAGE_ALERT tenant=920001 usage_type=ai_tokens threshold=80%
USAGE_ALERT tenant=920001 usage_type=ai_tokens threshold=100%
checked=2 delivered=2 retrying=0 failed=0
```

Database verification showed both records as `delivered`, each with one
attempt and a non-null UTC delivery timestamp. The temporary tenant, usage
events, and alerts were removed after verification.

Conclusion: threshold detection, transactional outbox persistence, independent
delivery, and final delivery-state recording work end to end. SMTP network
calls are mocked in automated tests so the suite does not require external
credentials or send real email.

---

## Monthly Invoice Evidence

Date verified: 2026-10-05

### Automated verification

Command: `python -m pytest -q`

Result: `76 passed in 1.85s`

The invoice tests cover UTC year boundaries, rejection of open months, frozen
base and overage line totals, exclusion of out-of-period usage, empty-month
statements, generation idempotency, authenticated reads, and safe job reruns.

### Migration and job probe

Alembic reported `a8d4e6f1c2b3 (head)`. The first September generation run
reported:

```text
checked=4 created=4 existing=0 failed=0
```

Repeating the same command reported:

```text
checked=4 created=0 existing=4 failed=0
```

This confirms that finalized tenant-month statements are not duplicated.

### Authenticated statement probe

`GET /invoices/1` returned one finalized September statement. Fetching its
detail through `GET /invoices/1/5` returned the same tenant, UTC period,
currency, totals, generation timestamp, and line-item collection. Tenant 1
had no September usage remaining in the local database, so the verified
statement correctly had a zero total and an empty line list. Automated tests
separately verify nonzero base and overage line items.
