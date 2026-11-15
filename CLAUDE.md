# Room Fit

Read `docs/HANDOFF.md` first. It defines the product, rules of engagement, and milestones. Never merge PRs; stay inside the current milestone.

## Commands
- Backend (from `backend/`): `python3.12 -m venv .venv && . .venv/bin/activate && pip install -e '.[dev]'`
  - Run: `uvicorn app.main:app --reload`
  - Check: `ruff check . && mypy app tests && pytest`
- Frontend (from `frontend/`): `npm install`
  - Run: `npm run dev`
  - Check: `npm run lint && npx tsc -b && npm test && npm run build`
