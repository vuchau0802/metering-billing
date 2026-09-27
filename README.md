# Usage Metering & Billing Engine

Metering, quota enforcement, cost calculation, and Stripe subscription sync for a multi-tenant SaaS.

The design — data model, quota rules, pricing math, and idempotency strategy — is in [`design.md`](design.md).

## Plans & quotas

| Plan | API calls / month | AI tokens / month |
|------|-------------------|-------------------|
| Free | 1,000 | 100,000 |
| Pro  | 50,000 | 5,000,000 |

The quota window is the **UTC calendar month**. A tenant may reach exactly its limit; the next request is the one refused.

## Pinned pricing constants

All money is an integer count of **micro-USD** (1 USD = 1,000,000 micro-USD). No floats touch a money value.

| Constant | Value (micro-USD per 1,000 units) | USD |
|----------|-----------------------------------|-----|
| `API_CALL_PRICE_PER_1K` | 2,000 | $0.002 / call |
| `INPUT_PRICE_PER_1K` | 150,000 | $0.15 / 1k tokens |
| `CACHED_INPUT_PRICE_PER_1K` | 75,000 | $0.075 / 1k tokens |
| `OUTPUT_PRICE_PER_1K` | 600,000 | $0.60 / 1k tokens |

Reasoning tokens bill at the **output** rate. Cached input tokens bill at half the input rate. Categories are costed separately and only then summed — see the cost formula in [`design.md`](design.md#pinned-pricing-constants).

These rates are illustrative and are not tied to any real provider's current pricing.

## Setup

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Copy the environment template and start PostgreSQL:

```powershell
Copy-Item .env.example .env
docker compose up -d
```

Apply the schema and seed demo data:

```powershell
alembic upgrade head
python seed.py
```

Start the API:

```powershell
uvicorn app.main:app --reload --port 8004
```

The API documentation is available at `http://localhost:8004/docs`.

Run the test suite:

```powershell
pytest -q
```
