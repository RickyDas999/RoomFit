# Decisions log

Running record of decisions we are going forward with. Newest last. Replaces `docs/ai-usage-log.md` (Ricky, 2026-11-15: stop using that file; it stays as-is, no new entries).

| Date | Decision | By |
|---|---|---|
| 2026-11-15 | Use pip + venv for the backend, Node 22 in CI, general-purpose agent for test-writer/reviewer roles. | Ricky |
| 2026-11-15 | ESLint (per handoff) and pin TypeScript to ~6.0, because typescript-eslint does not support TS 7 yet. | Ricky |
| 2026-11-15 | CI type check is `tsc -b` (the root tsconfig has `files: []`, so `tsc --noEmit` checks nothing). | Claude, found in M0 review |
| 2026-11-15 | Keep a decisions log instead of the AI usage log. | Ricky |
| 2026-11-15 | M1: add `agent-profile/ucp-profile.json` in the M1 PR; it declares only the catalog capabilities for now (checkout added in M6). | Ricky |
| 2026-11-15 | M1: country hard-coded to US (search `ships_to` and `context.address_country`). It is a prototype; no config. | Ricky |
| 2026-11-15 | M1: dev script uses a hard-coded 144 x 192 in sample room until M3 adds `room.py`. | Ricky |
| 2026-11-15 | M1: search query wording per role is a placeholder taken from the handoff examples; M3 refines it. | Claude (to confirm) |
