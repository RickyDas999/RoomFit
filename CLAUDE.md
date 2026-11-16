# Room Fit

Read `docs/HANDOFF.md` first. It defines the product, rules of engagement, and milestones. Never merge PRs; stay inside the current milestone.

## Commands
- Backend (from `backend/`): `python3.12 -m venv .venv && . .venv/bin/activate && pip install -e '.[dev]'`
  - Run: `set -a; . ./.env; set +a; uvicorn app.main:app --reload` (the app reads the Shopify credentials from the environment; without them `/api/recommend` returns 502)
  - Check: `ruff check . && mypy app tests scripts && pytest`
  - After changing the API: `python -m scripts.dump_openapi` (rewrites `backend/openapi.json`; a test fails if it is stale), then regenerate the frontend types.
- Frontend (from `frontend/`): `npm install`
  - Run: `npm run dev` (proxies `/api` to port 8000; use `API_URL=http://localhost:PORT npm run dev` for another port)
  - After an API change: `npm run gen:api` regenerates `src/api/schema.d.ts` from `backend/openapi.json`
  - Check: `npm run lint && npx tsc -b && npm test && npm run build`
- Checkout carts: the agent profile (`agent-profile/ucp-profile.json`) is served from `main` via jsDelivr. To try a profile that is not on `main` yet, start the backend with `UCP_PROFILE_URL=https://cdn.jsdelivr.net/gh/RickyDas999/RoomFit@BRANCH/agent-profile/ucp-profile.json`.
