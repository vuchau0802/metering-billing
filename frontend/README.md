# Usage Billing Dashboard

React and TypeScript customer dashboard for the usage metering and billing
engine.

## Development

Start FastAPI from the repository root:

```powershell
python run.py
```

Start Vite from this directory:

```powershell
npm install
npm run dev
```

Vite proxies `/api` requests to `http://localhost:8004`.

## Verification

```powershell
npm test
npm run lint
npm run build
```

Tenant credentials are stored in `sessionStorage` and sent to the backend using
the `X-Tenant-Key` header. Production authentication should use server-managed
sessions and secure HTTP-only cookies.
