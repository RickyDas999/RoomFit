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
- Agent profile: `agent-profile/ucp-profile.json` is served by jsDelivr from a **commit-pinned URL** (`PROFILE_URL` in `backend/app/catalog.py`), not from `main`, because Shopify caches a profile by URL and kept serving an old copy of the `@main` URL. **When the profile file changes, commit it, then point `PROFILE_URL` at that new commit** (a test fails if the pinned copy differs from the file). To try a profile that is not committed yet, start the backend with `UCP_PROFILE_URL=https://cdn.jsdelivr.net/gh/RickyDas999/RoomFit@BRANCH/agent-profile/ucp-profile.json`.
