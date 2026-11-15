# Room Fit

Read `docs/HANDOFF.md` first. It defines the product, rules of engagement, and milestones. Never merge PRs; stay inside the current milestone.

## Commands
- Backend (from `backend/`): `python3.12 -m venv .venv && . .venv/bin/activate && pip install -e '.[dev]'`
  - Run: `uvicorn app.main:app --reload`
  - Check: `ruff check . && mypy app tests scripts && pytest`
  - After changing the API: `python -m scripts.dump_openapi` (rewrites `backend/openapi.json`; a test fails if it is stale), then regenerate the frontend types.
- Frontend (from `frontend/`): `npm install`
  - Run: `npm run dev`
  - Check: `npm run lint && npx tsc -b && npm test && npm run build`
