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
