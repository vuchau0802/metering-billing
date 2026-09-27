# Build Log

An honest record of what was built, and where AI helped — including where it was wrong or missed something.

---

## Phase 1 — Design

**Status: complete.** Gate met: the design document is committed.

### What was built
- `design.md` — data model, plan quotas, pinned pricing constants, the `POST /generate` contract, the idempotency strategy, and the layer sketch.
- `.env.example` — every variable the app needs, with safe placeholders.
- `README.md` — plans, quotas, and the pinned pricing table.
- `capstone.yaml` — run/seed/base_url plus the endpoints an evaluator should probe.

### AI assistance
- **Where AI helped:** drafted the first pass of `design.md`; reviewed it line-by-line against the Phase 1 checklist in the capstone brief and produced the gap list below; wrote the revised schema and the corrected cost/quota rules in the current `design.md`.
- **What the first draft got wrong (caught in review, fixed):**
  - No `subscriptions` table — subscription status, `current_period_end`, and `cancel_at_period_end` had nowhere to live, even though the brief lists `subscriptions` as a required table and the `customer.subscription.updated` / `.deleted` webhooks need to write it.
  - No integer-money rule. The first draft wrote pricing constants as dollar floats (`$0.15`) and never specified the unit costs are stored in — a direct violation of the brief's ground rules.
  - No cost formula. The constants were listed but the arithmetic that combines them was not, so "reasoning tokens bill as output" and "categories are not additive" were asserted rather than specified.
  - `429` vs `402` was left as "429 or 402" with no rule for which applies — but Probe 2 grades boundary behaviour against a *documented* rule, so this had to be pinned before any code was written.
  - The quota window was "current month" with no statement of *which* month, and no stated behaviour for an upgrade mid-month.
  - `tenant.status` was missing despite the brief requiring webhooks to update plan **and** status.
- **What I changed and why:** each of the above is now explicit in `design.md` — integer micro-USD end to end, a `subscriptions` ledger table, the cost formula written out, the 429/402 table, the UTC calendar-month window, and `status` on `tenants`.

### Notes for me to expand in my own words
- Why I chose a **denormalized `plan` on `tenants`** *and* a separate `subscriptions` ledger, rather than deriving the plan with a join on every request.
- Why the **UTC calendar month** is the quota window instead of the Stripe billing period, and what that gives up.
- Why `cost_microusd` is **frozen on the usage event** instead of being recomputed at rollup time.

---

## Phase 2 — Core billing logic

**Status: complete.** Gate met: duplicate requests create one event, and quota
and entitlement boundaries return the documented status codes.

### What was built
- FastAPI application with `/health`, `/generate`, and `/usage/{tenant_id}`.
- PostgreSQL schema managed through Alembic migrations.
- Seeded Free and Pro plans plus active and past-due demo tenants.
- Integer-only pricing in micro-USD.
- UTC calendar-month quota calculation.
- Tenant row locking to serialize quota checks.
- Database-enforced idempotency through a unique idempotency key.
- Stored response snapshots and the `Idempotent-Replay` response header.
- Machine-readable 400, 402, 404, 409, and 429 responses.
- Unit and database-backed API tests.

### Verification
- `python -m compileall app` completed successfully.
- `pytest -q` reported 31 passing tests.
- Sending the same request twice returned identical bodies and one database
  event.
- Exact quota usage was accepted.
- One token beyond quota returned 429 without changing usage.
- A past-due tenant returned 402.

### AI assistance
AI helped translate the design into incremental service, repository, schema,
migration, and test code. I entered and ran each step, inspected the outputs,
and fixed issues as they appeared.

The initial SQLAlchemy enum declarations caused Alembic to generate an invalid
`metadata=MetaData()` expression. I removed the metadata argument from the
model enum declarations and generated migration expressions. After that
correction, upgrade and upgrade-to-head succeeded.

### Decisions to explain in my own words
- Why tenant rows are locked during quota checks.
- Why response snapshots are stored for idempotent replay.
- Why rejected quota requests never create usage events.
- Why money is stored as integer micro-USD.
