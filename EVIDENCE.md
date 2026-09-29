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
