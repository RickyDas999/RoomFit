# AI usage log

One entry per milestone; format in docs/HANDOFF.md section 9.

### M0: Scaffold and CI (2026-11-15)
- Asked by Ricky: post a plan for M0, then build it after approval. Ricky chose pip, Node 22, and the general-purpose agent for the subagent roles.
- What Claude Code did: scaffolded FastAPI (`/api/health`) and Vite React-TS, wired ruff/mypy/pytest and eslint/tsc/vitest, wrote the CI workflow, CLAUDE.md, .env.example.
- Subagents used: test-writer (general-purpose) found that `App.tsx` showed a blank status as healthy on an HTTP 500 with a JSON body; fixed. Reviewer (general-purpose) found that `tsc --noEmit` checked nothing because the root tsconfig has `files: []`; CI now uses `tsc -b`. It also flagged a stale Vite README and ignore gaps; fixed.
- Where Ricky overrode or corrected AI: none yet.
- What AI got wrong or couldn't do: shipped the unchecked `r.ok` fetch and initially said it was fine to leave; the Vite template's oxlint and TypeScript 7 conflicted with the handoff's ESLint, so TypeScript is pinned to ~6.0. The reviewer also wrongly claimed HANDOFF section numbers were mislabeled.
