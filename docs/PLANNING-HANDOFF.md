# Room Fit: build report for the planning agent

**What this is.** A summary of what was built from `docs/HANDOFF.md` (the plan you drafted with Ricky), how the result differs from that plan, and where to look in the repository to check anything yourself. Written Nov 16, 2026, after all milestones merged. Deadline for the whole project: **Wed Nov 18, 2026, 6:20 PM ET** (recording the ≤3-minute video is the main thing left).

**How to use it.** Read sections 1–3 for the picture. Sections 4–6 are the surprises and the open items you most likely need to act on. Section 7 is a reading order for the repo. Everything here is backed by the repo; paths are given so you can check.

---

## 1. Status in one paragraph

All seven planned milestones (M0–M6) are built, reviewed, CI-green and **merged by Ricky** (PRs #1, #2, #4, #5, #7, #9, #10), plus five pieces of work outside the plan that Ricky asked for or approved (PRs #3, #6, #8, #11, #12) and a README (#13). The app takes any room size, finds real Shopify products for each piece of furniture, places them to scale, checks the four hard clearance rules and the coverage rule, is explicit about how far each listing's size can be trusted, and makes one UCP **cart** per merchant with no purchase. Nothing about products is stored. Roughly 2,400 backend tests and 300 frontend tests pass with no credentials; the live paths were checked by hand against the real catalog and in a real browser.

One important departure: **the planned UCP checkout sessions could not be offered** (not one live product is eligible for native checkout), so M6 shipped the plan's documented fallback, carts. Details in section 4.

---

## 2. Plan versus built, milestone by milestone

| Milestone (plan) | PR | What shipped | Difference from the plan |
|---|---|---|---|
| **M0** Scaffold and CI | #1 | FastAPI `/api/health`, React/Vite app, ruff/mypy/pytest, eslint/tsc/vitest, one CI workflow with two jobs, `CLAUDE.md`, `.env.example` | CI uses `tsc -b` (the plan's `tsc --noEmit` checks nothing with project references). TypeScript is pinned to 6 for ESLint support. `docs/ai-usage-log.md` was created but **Ricky replaced it with `docs/decisions-log.md`** |
| **M1** Catalog client | #2, #3 | `catalog.py` (token held in memory, search, 429 + `Retry-After`), `search.py` (role + size to query), a dev script that prints live results and writes nothing | The plan hosted the agent profile at a raw GitHub URL. Raw GitHub serves `text/plain`, so Shopify answered 422 `profile_malformed`; it is now served by jsDelivr (#3). Search wording per role was approved by Ricky |
| **M2** Dimension parser | #4 | `dimensions.py`: regex only, returns a structured result (parsed / ambiguous / missing + reason), always W × D × H in inches, w and d must be 6–300 in | Ricky chose "null for ambiguous, as a structured response". Traps handled: shipping box sizes, mattress sizes, ranges, several sizes, quantities, fractions, feet+inches, cm/mm. The LLM extraction layer was **deferred** by Ricky (still a non-goal) |
| **M3** Fit engine | #5 | `room.py` (slots computed from the room), `fit.py` (every rule, coverage, verdict), `rules.py`, `/api/evaluate`, `/api/recommend` (cheapest listing that fits each slot) | Ricky confirmed several details the plan left open: the door path runs to the room's center line; the desk chair is always an assumed 20 × 20 in; overlaps and pieces outside the room are extra hard fails; furniture is oriented long side along the wall |
| **M4** Floor plan UI | #6, #7 | SVG plan to scale (walls, door swing, window, closet, pieces), shaded clearance zones that turn red with "N in short", product rows with swap, flags list, coverage meter | Needed two API additions first (zones and swap candidates), which Ricky asked for as a **separate small PR (#6)**. Frontend types are generated from `backend/openapi.json`; CI fails if they drift |
| **M5** Dimension depth | #9 | Confidence per product (stated / inferred / ambiguous / missing), `metadata.tech_specs` as the "inferred" source, rotation (each piece tried both ways), per-search data-gap numbers, a warning badge for inferred | **Plus** a bed size sanity check Ricky added (a "Queen" frame listed 55 in wide is rejected) |
| **M6** UCP checkout session, no purchase | #10 | `cart.py`, `POST /api/checkout` and `/api/checkout/cancel`, a Checkout panel with one cart per merchant, "Prototype: purchase disabled", cancel by button / on room change or swap / on page close | **Carts instead of checkout sessions** (section 4). The plan's `checkout.py` and `/api/checkout/{shop_id}` do not exist; the endpoint takes the whole layout and groups by shop on the server |

### Work outside the plan (all approved by Ricky)

| PR | What and why |
|---|---|
| #3 | Profile hosting fix (above) |
| #6 | Zones and candidates in the API (above) |
| #8 | **Scenarios.** Ricky noticed that moving the door onto where furniture had been left pieces with no usable space, and that changing the requirements did not change the result. Added: a `needs` list (checkboxes: nightstand, dresser, desk + chair; the bed is always needed); bed size that follows the room (Twin XL, Full, Queen, King, auto or chosen); planner fallbacks when a needed slot has no space (mirror to the other side, or put the desk on the door wall beside the dresser); and seven preset example rooms. Slots are still computed, not drag-and-drop, so the plan's non-goal "auto-layout" still holds |
| #11 | **Storefront restyle.** The planner is shown as a page of a placeholder store ("Northfield Home") with a decorative header, nav and footer (no links, nothing focusable), light theme only, list rows instead of cards. Frontend only; no backend change |
| #12 | **Storyboard audit** (section 5): a "Narrow bedroom" example, a badge for every confidence class, and a commit-pinned agent profile URL |
| #13 | README with two screenshots (no product data in them) |

---

## 3. The plan's rules, and whether they held

| Rule or non-goal in `HANDOFF.md` | Held? |
|---|---|
| Never merge, never push to `main` | Yes. Ricky merged all 13 PRs |
| One milestone = one branch = one PR; plan first, wait for approval | Yes. Extra work (scenarios, restyle, audit, README) also got a plan or a direct request first |
| Test-writer and reviewer subagents each milestone | Yes. They found real bugs each time (for example: a quadratic regex, a stale-state race in the UI, a 500 from one malformed shop answer that orphaned other shops' carts, an SSRF-style input check). Fixes and the rest are in each PR description |
| Stay inside the milestone; follow-ups go in the PR | Yes |
| Fit rule values (36 / 24 / 24 / 18 in, coverage 40 / 45%) in `rules.py` with sources | Yes: `backend/app/rules.py` |
| Stateless: store no Shopify product data | Yes. No database, no files; tests use made-up listings and mocked HTTP; the README screenshots avoid product data |
| Never complete a purchase, never call `complete_checkout` | Yes. A test greps the source for the tool name; another checks only cart tools are ever called |
| No floor plan upload, no auto-layout or drag-and-drop, no LLM, no color matching | Yes (see "Future work" in the README) |
| No secrets in the repo or in chat | Yes. `.env` is git-ignored; credentials were never read or printed |
| Decisions belong to Ricky | Yes. Every decision is a row in `docs/decisions-log.md` with who made it |

---

## 4. Where reality differed from the plan's assumptions (the findings that matter)

1. **No live product is eligible for native checkout.** In 12 furniture searches (600 products), `eligible.native_checkout` was `false` for every one. The plan's checkout section assumed some products would work and said to offer checkout only for those. So M6 used the plan's own fallback: **UCP carts**, made anonymously at each merchant (no token, no buyer IP, so the user's IP is never sent), with a link to continue on the merchant's site. Carts work for any Shopify product. If merchants enable native checkout later, real checkout sessions are a follow-up that needs a decision about the buyer IP.
2. **Shopify caches the agent profile by URL.** After the cart capability was added to the profile and merged, Shopify kept answering "Tool not found: create_cart" for the `@main` URL while a commit-pinned URL worked immediately. `PROFILE_URL` in `backend/app/catalog.py` is now pinned to a commit, a test fails if the pin and the profile file disagree, and `CLAUDE.md` explains the procedure. **The profile also had to declare the cart and checkout capabilities**; the plan declared catalog only.
3. **Dimensions are even scarcer than assumed.** Live numbers: for desks, about 21 of 25 listings state a usable size; for beds, as few as 5 of 25; the last full run across five roles was 48 of 125 usable (36 stated + 12 inferred). `metadata.tech_specs` (a list of "Label: value" strings, present on most products) lifted that from 36 to 48. Sizes can also be wrong in ways that look fine, which is why the bed size check exists.
4. **The 18 in chair rule is hard to trip.** In the sample room the clearance beside the bed (24 in) is stricter than behind the chair (18 in) and sits in the same place, so with real desks the bed rule breaks first. Storyboard moment 3 is therefore shown in a **"Narrow bedroom" example** (section 5).
5. **The bed slot is half the room.** Because the door path runs to the room's center line (Ricky's decision), the bed gets only the far half of the room's depth. A Twin XL frame (about 84 in) therefore needs a room about 14 ft deep in the standard layout. Shallower rooms correctly say "no bed fits under these rules."

---

## 5. Storyboard status (plan section 9)

| Moment | State |
|---|---|
| 1. Enter the room (~200 sq ft) | Works. The sample room is 144 × 192 in (192 sq ft); any size is accepted |
| 2. Real products that fit, with dimensions shown | Works. Each row shows the size and the text it came from |
| 3. Swap in a bigger desk and the 18 in chair flag fires | Works **only in the "Narrow bedroom" example** (124 × 192 in, no closet): the cheapest desk fits; the 60 × 60 in L-shaped desk then breaks the bed side (19 in short) and the chair (13 in short). In the 12 × 16 ft sample room it breaks only the bed side. The video script (or storyboard step 3) should name the Narrow bedroom |
| 4. The data gap, with confidence badges | Works. "Of 25 desks Shopify returned, 21 list usable dimensions (19 stated, 2 inferred)" per piece, a total line, and a badge per class: stated, inferred, size unclear, dimensions missing |
| 5. Per-merchant checkout with a handoff, no purchase | Works as **carts** (section 4). Verified live: 5 of 5 carts made at 5 shops, then cancelled |

---

## 6. Open items and things you will want to decide

**Decisions logged but not explicitly confirmed by Ricky** (their PRs were merged, but their rows in `docs/decisions-log.md` still say "to confirm"): the M2 rows about repeated sizes and the 4+ numbers / quantity rules; the four M5 rows (confidence classes, tech_specs label rules, the bed size check rules, rotation and its tie-break); the storyboard-audit row (Narrow bedroom, badge wording). Worth asking Ricky for a quick yes so the log is clean.

**`docs/HANDOFF.md` is stale in these places** (it is Ricky's doc; nothing was edited):
- Section 6, profile: still a raw.githubusercontent URL; now jsDelivr pinned to a commit, with cart and checkout capabilities.
- Section 6, UCP checkout and section 3 (`checkout.py`) and M6: carts, `cart.py`, endpoint names, and no buyer-IP header.
- Sections 2 and 9: `docs/ai-usage-log.md` is unused; Ricky chose `docs/decisions-log.md`.
- Section 7: no mention of M4a, scenarios, restyle, audit or README; M5 lacks the size check; M6 is carts.
- Section 9 step 3: assumes the sample room.
- Section 3: `tsc --noEmit` is `tsc -b`; types are generated with a pinned `npx openapi-typescript@7.13.0` because the package supports only TypeScript 5.

**Known limits** (all also in the README): fixed slots with fallbacks, not a real layout search; US and USD only; results change between runs; the chair is always an assumed 20 × 20 in; King and other frames can still carry wrong sizes the checks cannot detect; a prototype-grade input check on the cart shop address (a public hostname that resolves to a private address is not blocked; the server only POSTs JSON to port 443 with size and time limits); closing the tab cancels carts, including one a person opened in another tab to pay.

**Questions for the plan:** the video itself (script, which examples to show, one sitting because results change, the 3-minute cut); a license (none chosen); whether to keep the "built with Claude Code" paragraph in the README; whether to extend the build or freeze it.

---

## 7. How to look into the repository

**Reading order (about 30 minutes):**
1. `README.md`: what it does, how it works, how to run and test.
2. `docs/HANDOFF.md`: the original plan, so you can compare as you read.
3. `docs/decisions-log.md`: **the best single source for "what was decided, by whom, and why"** (one row per decision, in date order; "Ricky" means he decided it).
4. `CLAUDE.md`: commands and the profile-pinning procedure.
5. `backend/app/rules.py` (every rule value) → `room.py` (slots, planner, fallbacks) → `fit.py` (checks, zones, verdict) → `dimensions.py` (parser) → `catalog.py` (Shopify client, confidence classes) → `beds.py` (sizes) → `cart.py` (carts) → `main.py` (routes and the recommend loop).
6. `frontend/src/App.tsx` (state and flow), `components/` (form, floor plan, product rows, flags, checkout panel, store chrome), `scenarios.ts` (the seven examples), `api/` (client and generated types).
7. `agent-profile/ucp-profile.json` and `backend/openapi.json` (the API contract).

**Questions and where to answer them:**
- *What did each PR change and why?* `gh pr list --state merged` and `gh pr view N` (every PR has what / how to try / tests / reviewer findings / decisions / follow-ups).
- *Is rule X implemented as planned?* `backend/app/rules.py` and `backend/tests/test_fit.py`.
- *What counts as a usable size?* `backend/tests/test_dimensions*.py` and `test_m5*.py`.
- *Why carts, and is the checkout guardrail real?* decisions-log rows dated 2026-11-16 starting "M6", and `backend/tests/test_api_fit.py` (the source grep) and `test_cart.py`.
- *Does storyboard moment 3 hold?* `backend/tests/test_storyboard.py`.
- *What does each example room do?* `frontend/src/scenarios.ts` and `backend/tests/test_scenarios.py`.

**To run it** (needs Ricky's Shopify credentials in `backend/.env`; **never ask for them in chat and never print them**): follow "Getting started" in the README. The tests need no credentials:

```bash
cd backend && . .venv/bin/activate && ruff check . && mypy app tests scripts && pytest
cd frontend && npm run lint && npx tsc -b && npm test && npm run build
```

**Live-data tools** (print only, write nothing, need credentials): `python -m scripts.dev_catalog` and `python -m scripts.dimension_report` from `backend/`. The second prints the data-gap numbers used in the video.

**Rough size:** 77 commits on `main`; about 2,200 lines of backend code and 1,400 of frontend code (without tests); 21 backend test files and 18 frontend test files.
