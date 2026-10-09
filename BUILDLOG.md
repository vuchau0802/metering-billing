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

---

## Phase 3 - Stripe integration

**Status: complete.** Gate met: a Stripe test-mode Checkout changed a seeded
tenant from Free to Pro through verified webhooks.

### What was built
- Stripe test-mode Checkout Session creation for Free tenants.
- Existing Stripe customer reuse when a tenant already has a customer ID.
- Raw-body Stripe webhook signature verification.
- Database-backed webhook event deduplication.
- Synchronization for `checkout.session.completed`.
- Synchronization for subscription created, updated, and deleted events.
- Subscription status, billing period, and cancellation persistence.
- Tenant plan and entitlement-status synchronization.
- Checkout success and cancellation redirect endpoints.
- Automated tests for signatures, replay, upgrades, subscription lifecycle,
  and redirect responses.

### Verification
- `python -m compileall app tests` completed successfully.
- `python -m pytest -q` reported 37 passing tests.
- Stripe CLI forwarded `customer.subscription.created` with HTTP 200.
- Stripe CLI forwarded `checkout.session.completed` with HTTP 200.
- Tenant 1 changed from `free active` to `pro active`.
- The Stripe customer ID, subscription ID, active status, and UTC billing
  period were persisted.
- A second Checkout attempt for tenant 1 returned `already_subscribed`.

### AI assistance
AI helped divide the integration into repository, service, endpoint, and test
steps. I entered each change, ran the tests, and verified the real Stripe flow
locally.

A webhook test exposed that Stripe SDK resource objects do not implement the
dictionary `.get()` method. Converting `event["data"]["object"]` with
`.to_dict()` fixed the integration. The first Stripe CLI command also passed
an unquoted event list in PowerShell, which Stripe interpreted as one invalid
event name. Quoting the comma-separated list fixed local forwarding.

### Decisions to explain in my own words
- Why signatures are verified against the untouched request body.
- Why the processed event marker and subscription update commit together.
- Why Checkout metadata carries the internal tenant ID.
- Why canceled subscriptions revert the tenant plan to Free.

---

## Phase 4 - Cost and finalization

**Status: complete.** Gate met: `/usage` matches the pinned pricing constants,
and the final acceptance and repository audits pass.

### Background reconciliation
- Added a standalone Stripe subscription reconciliation command.
- Reused the same subscription synchronization logic as verified webhooks.
- Added three-attempt exponential retry behavior.
- Added critical failure logging and a nonzero process exit code.
- Added tests for transient recovery, persistent failure, and alert signaling.

### Verification
- `python -m pytest -q` reported 40 passing tests.
- Live reconciliation retrieved one Stripe subscription with HTTP 200.
- The job reported `checked=1 succeeded=1 failed=0`.
- PostgreSQL remained synchronized as `pro active` with the correct active
  subscription and UTC billing period.
- `GET /usage/1` returned the Pro limits, 1,800 used AI tokens, and the
  expected frozen cost of 367,500 micro-USD.
- Alembic reported `e5ca33e8ba3d (head)` as both the available and applied
  migration head.
- Required submission files and ignore rules were present.
- No Stripe secret patterns were found in tracked files or Git history.

### AI assistance
AI helped extract webhook synchronization into reusable logic and design the
standalone reconciliation command. I entered and tested the implementation.
The initial refactor renamed the function definition without updating both
dispatcher calls, causing one test failure. Updating both references restored
the suite to green.

---

## Review hardening

**Status: complete.** The external review findings are addressed and the full
suite passes with tenant isolation enabled.

### What changed
- Added hashed per-tenant API keys and `X-Tenant-Key` authorization to usage,
  metering, and Checkout routes.
- Rejected all-zero AI token requests before they can create usage events.
- Moved webhook deduplication races into a savepoint so repositories never
  roll back a caller-owned transaction.
- Kept raw-body Stripe signature verification while running the synchronous
  webhook handler and SQLAlchemy session in FastAPI's threadpool.
- Made tenant seeding preserve Stripe-managed plan and entitlement state.
- Added regression coverage for authentication, zero usage, and safe seeding.

### Verification
- Alembic upgraded to `c91b2f6e4a7d (head)`.
- Reseeding completed without changing the existing Stripe subscription state.
- `python -m pytest -q` reported 48 passing tests.

---

## Stretch Goal - Overage Billing

**Status: complete.**

- Free plans remain hard-capped.
- Pro plans accept usage beyond quota.
- Overage units and surcharges are frozen on each usage event.
- Usage rollups expose cumulative overage and overage cost.
- Month-end projected cost uses deterministic integer arithmetic.
- Idempotent replay returns the original frozen billing response.
- Alembic added the overage fields in revision `4ae70d2a0651`.
- The full suite reports 55 passing tests.

---

## Stretch Goal - Usage Alerts

**Status: complete.**

### What was built
- Durable 80% and 100% quota-threshold alerts for API calls and AI tokens.
- Alert creation in the same database transaction as the usage event.
- Database uniqueness across tenant, usage type, UTC window, and threshold.
- A transactional outbox worker using `FOR UPDATE SKIP LOCKED`.
- Logging and SMTP notification transports behind a notifier interface.
- Retry counters, captured errors, delivery timestamps, and terminal failure
  state after the configured maximum attempts.
- Bounded worker batches and protection against retrying one failed alert in a
  tight loop during the same run.

### Verification
- `python -m pytest -q` reported 70 passing tests.
- A manual Free-tenant probe crossed 80% and then 100% of the AI-token quota.
- The database contained exactly two pending alerts, one for each threshold.
- The worker logged both notifications and reported
  `checked=2 delivered=2 retrying=0 failed=0`.
- Both records finished as delivered with one attempt and a UTC timestamp.

### AI assistance
AI helped structure the feature as transactional detection plus an independent
delivery worker, and suggested deterministic tests for retries and SMTP. I
entered and ran each step, diagnosed a test-cleanup foreign-key failure, and
verified the complete flow against PostgreSQL.

### Decisions to explain in my own words
- Why alert creation belongs in the usage transaction but delivery does not.
- Why threshold comparisons use integer arithmetic.
- Why the outbox has a unique constraint in addition to application checks.
- Why workers use row locks with `SKIP LOCKED`.

---

## Stretch Goal - Monthly Invoices

**Status: complete.**

### What was built
- Finalized monthly statement headers and immutable usage-type line items.
- Frozen event count, quantity, base cost, overage quantity, overage cost, and
  total cost using integer micro-USD.
- One invoice per tenant and completed UTC month, enforced by PostgreSQL.
- A rerunnable monthly generation command for the previous UTC month.
- Authenticated invoice list and detail endpoints with tenant isolation.
- Zero-total statements for months without activity.

### Verification
- Alembic upgraded to `a8d4e6f1c2b3 (head)`.
- `python -m pytest -q` reported 76 passing tests.
- The first live generation run reported
  `checked=4 created=4 existing=0 failed=0`.
- Repeating it reported `checked=4 created=0 existing=4 failed=0`.
- Tenant 1's authenticated list and detail endpoints returned its finalized
  September statement.

### Decisions to explain in my own words
- Why only completed UTC months can be finalized.
- Why invoice lines copy frozen usage-event values instead of recalculating
  historical prices.
- Why empty months still produce statements.
- Why the unique tenant-period constraint is required even with job checks.

---

## Stretch Goal - Mid-Cycle Upgrade Proration

**Status: complete.**

### What was built
- Deterministic Free-to-Pro proration through the next UTC-month boundary.
- Integer round-half-up calculations in micro-USD with exact boundary tests.
- Immutable billing adjustments keyed uniquely by Stripe event ID.
- Replay-safe handling regardless of whether Checkout or subscription events
  arrive first.
- Checkout billing-cycle anchoring so Stripe and the local ledger use the same
  period.
- Monthly statement integration with separately exposed adjustments.
- Late adjustments roll into the next open statement instead of mutating a
  finalized invoice.

### Verification
- Alembic added billing adjustments in revision `6f5d232a275d`.
- `python -m pytest -q` reported 88 passing tests.
- A live Stripe test-mode Checkout created one local adjustment and one Stripe
  proration invoice line for a temporary tenant.
- The local `7,376,990` micro-USD calculation rounded to 738 cents; Stripe's
  invoice reported `amount_due=738`, `amount_paid=738`, and `total=738`.
- Canceling the subscription produced the expected local `free canceled`
  entitlement state.

### Decisions to explain in my own words
- Why Stripe and the local ledger must share the same billing-cycle boundary.
- Why money is calculated with integers rather than floating point.
- Why the adjustment is frozen and keyed by the source webhook event.
- Why a late adjustment must not modify a finalized statement.
