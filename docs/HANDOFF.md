# Room Fit: Claude Code handoff

> **Status: v5 (Nov 14, 2026). All decisions settled.** Repo: `RickyDas999/RoomFit` (https://github.com/RickyDas999/RoomFit). Do not start a milestone until Ricky says to start it.

Put this file in the repo at `docs/HANDOFF.md`, and have `CLAUDE.md` point to it. Ricky owns every product decision. You (Claude Code) are the implementation agent. A separate planning agent drafted this doc with Ricky, and Ricky edits it.

---

## 1. What we're building

A web app for first-time renters and home buyers. You enter one room's floor plan and get a set of real Shopify products that **fit together** in it with comfortable walking space, and can be bought through a UCP checkout. **The focus is dimensions** (Ricky decided Nov 14): getting reliable sizes out of listings, placing them, and being honest when data is missing.

- **Any room size.** The user enters the room's width, depth, door, window and closet. The demo default is Ricky's ~12 × 16 ft college bedroom, but nothing is hard-coded to it.
- **Stateless product data.** Products are fetched live from the Catalog API for each request, based on the room, and are never stored (section 6).
- **Deliverable:** a working prototype that gets screen-recorded for a ≤3-minute video. Aim for clarity over polish. The total build budget is about 2–3 hours of Ricky's time.
- **Deadline:** Wed Nov 18, 2026, 6:20 PM ET. Leave at least a day for recording.

### Non-goals (do not build)
- Floor plan upload or parsing (future feature).
- Auto-layout or drag-and-drop placement (future feature). We use fixed slots.
- An LLM or agentic layer for dimension extraction. Pattern matching only for now. Ricky will decide later whether messy data needs more.
- Completing a purchase. **Never call `complete_checkout`.**
- Color, palette or theme matching, and the "complete this look from one shop" suggestion (future features, section 11).
- Storing Shopify product data in a database or file.
- Accounts, login, payments, or deployment to production.

---

## 2. Rules of engagement (how you work)

These rules are not negotiable.

1. **Never merge.** Never merge a PR, never push to `main`, never force-push `main`, and never enable auto-merge. Ricky reviews and merges every PR.
2. **One milestone = one branch = one PR.** Branch name `m<N>-<short-name>` (e.g. `m2-dimension-parser`), cut from the latest `main`. Don't start milestone N+1 until Ricky has merged milestone N, unless Ricky says to stack.
3. **Stay inside the milestone.** Only build what the current milestone's scope lists. If you find something that needs doing outside it, write it under "Follow-ups" in the PR. Don't build it.
4. **Don't make product decisions.** If something is ambiguous (a rule value, a UI choice, which product to show), stop and ask Ricky. Never invent a rule value. All values live in `backend/app/rules.py`, and they match section 5.
5. **Small, readable commits.** Use conventional prefixes (`feat:`, `test:`, `fix:`, `chore:`, `docs:`). Ricky has to be able to explain every line in an interview, so prefer simple code over clever code.
6. **Secrets.** Credentials come from `.env` (gitignored) only. Commit `.env.example` with empty values. CI never needs secrets.

### Per-milestone loop
For every milestone, in this order:
1. **Plan.** Post a short plan (files to touch, approach, tests) and wait for Ricky's OK.
2. **Implement** on the milestone branch.
3. **Test.** Write tests for the milestone's acceptance criteria. Use the **test-writer subagent** for an independent pass at edge cases.
4. **Review.** Start a **reviewer subagent** with fresh context. Give it the diff, this doc, and the milestone's acceptance criteria, and ask for correctness bugs, scope creep, and anything that breaks section 2. Fix what it finds, or explain in the PR why you didn't.
5. **CI.** Push, and confirm GitHub Actions is green. If it's red, fix the cause. Never skip, disable, or weaken a test to get green.
6. **Open the PR** using the template in section 8. Assign Ricky and request their review.
7. **Log.** Append an entry to `docs/ai-usage-log.md` (section 9).
8. **Stop** and wait for Ricky.

---

## 3. Stack and repo layout

- **Frontend:** React + TypeScript, built with Vite. Tests: Vitest + React Testing Library. Lint: ESLint. Type check: `tsc --noEmit`.
- **Backend:** Python 3.12 + FastAPI. Make HTTP calls with `httpx`. **No database and no product persistence** (Ricky decided Nov 14). The room arrives in each request body. Tests: pytest. Lint/format: ruff. Types: mypy (or pyright).
- **API types:** FastAPI generates OpenAPI. Generate TypeScript types from it with `openapi-typescript` so the frontend and backend can't drift.
- **CI:** GitHub Actions, one workflow with two jobs, `backend` (ruff, mypy, pytest) and `frontend` (eslint, tsc, vitest, build). It runs on every push and PR.

```
RoomFit/                   # github.com/RickyDas999/RoomFit
  CLAUDE.md                  # points to docs/HANDOFF.md, lists commands
  docs/HANDOFF.md            # this file
  docs/ai-usage-log.md       # per-milestone AI log (section 9)
  docs/decisions.md          # mirror of the decisions doc (Ricky maintains)
  backend/
    app/main.py              # FastAPI app and routes
    app/catalog.py           # Global Catalog MCP client (search, lookup)
    app/checkout.py          # UCP checkout client (create, get, cancel; NO complete)
    app/dimensions.py        # pattern-matching dimension parser
    app/fit.py               # fit engine: clearances, coverage, core needs
    app/rules.py             # every rule value, one place
    app/room.py              # sample room + slot definitions
    app/search.py            # turns a room's slots into catalog queries
    tests/
  frontend/
    src/...                  # floor plan SVG, product panel, flags, checkout
  agent-profile/ucp-profile.json   # our UCP agent profile (section 6)
  .github/workflows/ci.yml
```

---

## 4. Domain model

All lengths are in **inches**. The origin is the room's top-left corner, x goes right, y goes down.

- **Room:** `width`, `depth`, `door` (wall, offset, width, swing), `window` (wall, offset, width), `closet` (rect, fixed, not for sale).
- **Slot:** `id`, `role` (`bed` | `desk` | `desk_chair` | `dresser` | `nightstand`), `anchor` (wall and corner), `max_footprint` (w × d the slot allows), and `facing` (which side needs clearance).
- **Product:** `id` (`gid://shopify/p/...`), `variant_id`, `title`, `shop` (`id`, `name`, `domain`), `price` (minor units + currency), `image_url`, `url`, `native_checkout` (bool), `dimensions` (`{w, d, h}` or `null`), `dimension_source` (the matched text snippet, or `null`).
- **Layout:** a map of slot id to product id, plus the placed rectangles.
- **Evaluation:** `hard_fails[]` (each one names the rule, the pieces involved, and the inches short), `coverage_pct`, `missing_needs[]`, and `verdict` (`fits` | `cramped` | `incomplete`).

### Rooms and slots (Ricky decided Nov 14)
- The room is **user input**, any size. The frontend has a form (width, depth, door wall + offset, window wall + offset, closet yes/no) and a top-down preview.
- **Demo default:** 12 ft × 16 ft (144 × 192 in, 192 sq ft), close to Ricky's college bedroom. One door on a short wall, a window opposite, a 24 in-deep closet.
- **Slots are computed from the room**, not fixed coordinates. Each slot is anchored to a wall or corner, and its `max_footprint` is whatever space is left after clearances. Example: the desk slot's max depth = wall-to-path distance − 18 in chair clearance − chair depth.
- If a room is too small for a slot, say so ("no desk fits under these rules") rather than forcing a placement. That's a valid result.

---

## 5. Fit rules (Ricky confirmed Nov 15)

Put these in `rules.py` exactly as written. Each one cites its source in a comment.

| Rule | Value | Type | Source |
|---|---|---|---|
| Clear path from the door | 36 in | Hard | Hunker (3 ft); Comfyco |
| Open side of the bed | 24 in (a twin may sit against a wall) | Hard | Hunker (2 ft); Houzz (20–22 in) |
| In front of dresser and closet | 24 in | Hard | Hunker (2 ft) |
| Behind the desk chair | 18 in | Hard | Hunker (18 in) |
| Floor covered by furniture | ≤ ~40–45% (warn above 40, flag above 45) | Soft | Adapted from 60/40 (Apartment Therapy, Comfyco). Our own number |
| Too empty | a core need is missing: sleep (bed), study (desk + chair), storage (dresser or closet) | Soft | Our own definition |

A product with `dimensions: null` **can't be placed**. Show it as "dimensions missing" and never guess. That label is the platform critique, shown live.

---

## 6. Shopify integration (from the docs, read Nov 14–15)

### Ricky's setup steps (before M1)
1. Done by Ricky (Nov 14). The current Dev Dashboard (it needs a free Partner organization) has no "Catalogs" item. Credentials live under **Agents** on the `default` agent: **API key** = `SHOPIFY_CLIENT_ID`, **Client secret** = `SHOPIFY_CLIENT_SECRET`. Ricky puts both in `backend/.env` themselves. **Never ask Ricky to paste them into chat, and never print or log them.** The agent's Name is shown to merchants at checkout. Redirect URLs are unused.
2. Optional, for learning: install Node 22.19+, run `npm install -g @shopify/ucp-cli`, and try `ucp catalog search --set /query='twin xl bed frame' --set /context/address_country=US --view :compact --format md`.

### Catalog (Global Catalog, MCP over HTTP JSON-RPC)
- Get a token with `POST https://api.shopify.com/auth/access_token`, body `{"client_id","client_secret","grant_type":"client_credentials"}`. It expires after 60 minutes, so refresh it as needed. Send it as `Authorization: Bearer <token>`.
- Endpoint: `POST https://catalog.shopify.com/api/ucp/mcp`, using `"method":"tools/call"` with `search_catalog`, `lookup_catalog` (1–50 ids) or `get_product`.
- Every call includes `arguments.meta["ucp-agent"].profile` = our agent profile URL. The profile declares `dev.ucp.shopping.catalog.search`, `dev.ucp.shopping.catalog.lookup` and `dev.shopify.catalog.global`. Options were: host our own `agent-profile/ucp-profile.json` at a public HTTPS URL (public repo raw file, GitHub Pages, or a public gist), or use Shopify's example profile URL. Ricky decided (Nov 14): **host our own**, declaring only the catalog and checkout capabilities we use. The repo is public, so the profile is served from it as a raw GitHub URL: `https://raw.githubusercontent.com/RickyDas999/RoomFit/main/agent-profile/ucp-profile.json` (it goes live once M0 is merged to `main`).
- Useful search fields: `query`, `filters.price {min,max}` (minor units), `filters.ships_to`, `filters.shops`, `filters.attributes` (Color), `context.address_country`, and `pagination.limit` (max 50).
- Read: `products[].id/title/description/media/variants[]`, `variants[].id/price/checkout_url/eligible.native_checkout/seller{id,name,domain}`. Dimensions are **not** a field. The parser reads `description` (and `metadata.tech_specs` if present, which is ML-inferred and may be wrong).
- Rate limit: 5 req/s. On a 429, honor `Retry-After` and back off.

### Stateless product data (Ricky decided Nov 14)
Shopify's usage guidelines cap caching (product metadata and images 24 h, price and availability 10 min) and forbid a standing product database. Ricky chose to **store nothing**:
1. The frontend sends the room to `POST /api/recommend`.
2. The backend computes each slot's `max_footprint` from the room.
3. For each slot it calls `search_catalog`, in parallel and within the 5 req/s limit, with a query built from the role and size (e.g. "twin xl bed frame", "small desk 40 inch"), `filters.ships_to`, `available: true`, and `pagination.limit` 25–50.
4. It parses dimensions in memory, runs the fit engine, and returns the products plus evaluation to the browser.
5. Nothing is written to disk. Swaps and re-evaluations send the products back from the browser's state, or re-query.
- The only server-side cache is the OAuth token (in memory, 60 min).
- **Tests and CI use synthetic fixtures** (made-up listings shaped like real responses) and mocked HTTP, never saved Shopify data.
- Trade-offs to accept: results can change between runs (record the demo in one sitting), and each recommend takes a few seconds (show a loading state). Sorting is deterministic: cheapest product that fits.
- Video talking point: "I read the catalog terms, so the app stores no product data. It asks Shopify fresh for every room."

### UCP checkout (per merchant, at `https://{shop-domain}/api/ucp/mcp`)
- `create_checkout` takes `currency`, `line_items[{quantity, item.id = variant gid}]` and `buyer {email}`. Then `get_checkout`, and `cancel_checkout` (with an idempotency-key UUID) to clean up.
- Buyer email is a reserved test address (`demo@example.com`), so no real person is contacted.
- **Human in the loop, by design.** The app creates the session and shows what the merchant returned (status, line items, totals, `continue_url`). Paying is only possible if a human clicks through to the merchant's own checkout. The app never holds payment details. After the demo it calls `cancel_checkout`.
- Auth requires a bearer token **plus a `Shopify-Buyer-IP` header** (the buyer's real IP). The backend forwards the browser's IP. Anonymous calls can't use checkout.
- Show the returned `status`, `totals` and `continue_url`. Don't log `continue_url`. Require `https:`.
- **Hard guardrail:** `complete_checkout` must not exist anywhere in the code. A test greps the source and fails if it appears.
- Only offer checkout for products with `eligible.native_checkout = true`. Pick demo products accordingly.
- **Known unknowns (M6 starts with a 20-minute spike):** whether the agent API key can make checkout calls (likely, since the dashboard says the agent name is shown at checkout), and whether a localhost IP is accepted as the buyer IP. **Fallback if blocked:** create a UCP **cart** (Cart MCP takes unauthenticated calls) and hand off to the variant's `checkout_url`, then say so in the video.

Sources: shopify.dev/docs/agents/catalog, /agents/catalog/global-catalog, /agents/get-started/authentication, /agents/profiles/auth-and-rate-limiting, /agents/carts-and-checkout/checkout-mcp, /agents/get-started/quickstart, ucp.dev/latest/specification/overview.

---

## 7. Milestones

Each milestone is a PR. The time estimates are Claude Code time plus Ricky's review.

### M0: Scaffold and CI (~20 min)
- **Before M0:** the repo is empty and has no `main` yet, so there's nothing to branch from. Ricky adds a README through GitHub's web UI ("Add a README") to create `main`. Then M0 branches from it as normal.
- **Scope:** repo layout above, Vite React-TS app, FastAPI app with `GET /api/health`, ruff/mypy/pytest, eslint/tsc/vitest, the CI workflow, `CLAUDE.md`, `.env.example`, and an empty `docs/ai-usage-log.md`.
- **Done when:** CI is green on the PR, `npm run dev` and `uvicorn` both start, and the frontend shows the health response.

### M1: Catalog client and curated products (~30 min; needs Ricky's API key)
- **Scope:** `catalog.py` (token fetch with in-memory reuse, `search_catalog`, retry on 429 with `Retry-After`) and `search.py` (role + max footprint → query and filters). Add a dev-only script that prints live results for each role (shop, price, native-checkout flag, description snippet) to the terminal, **writing nothing to disk**, so Ricky can see the real data.
- **Done when:** unit tests pass on synthetic fixtures (mocked HTTP), the dev script runs against the live API locally, and a test asserts the catalog module writes no files.

### M2: Dimension parser (~25 min)
- **Scope:** `dimensions.py`. Parse formats like `39"W x 80"D x 14"H`, `39 x 80 x 14 in`, `Width: 39 in`, `99 cm` (convert), and `3.3 ft`. Return `{w,d,h}`, the matched snippet, or `null`. Add a report endpoint or script: "X of N products had parseable dimensions."
- **Done when:** a table-driven test covers each format plus traps (shipping box size, "fits mattress up to 80 in," a seat height alone). That X-of-N number goes in the video.

### M3: Fit engine (~30 min)
- **Scope:** `room.py` (the sample room and slots), `fit.py` (place a product in its slot, compute every hard clearance, coverage %, missing needs, verdict), and `POST /api/evaluate` taking a layout. Add `POST /api/recommend` (room in, live search per slot, fit, response out), which picks the **cheapest product that fits** each slot with no hard fails. Ricky decided this. It reflects the budget of first-time renters, and the UI labels it "sorted by: lowest price that fits."
- **Done when:** pure-function tests cover each rule at the boundary (exactly 18 in passes, 17.9 fails) and a known-good and known-bad layout. Swapping in an oversized desk produces the "behind the desk chair: 6 in short" fail.

### M4: Floor plan UI (~35 min)
- **Scope:** a top-down SVG drawn to scale. Shows walls, door swing, window, closet, placed products, and **shaded clearance zones** (red when broken). Side panel per slot: product card (image, title, shop, price, dimensions + source snippet, or a "dimensions missing" badge) and a "swap" list of alternatives. A flags list and a coverage meter.
- **Done when:** component tests cover the flags list and the swap action, and you can manually click through storyboard moments 1–3 (section 10).

### M5: Dimension depth (~25 min)
Ricky chose these three items (Nov 14). Near-miss explanations were considered and cut.
- **Confidence per product:** `stated` (clear W × D × H in the description), `inferred` (from Shopify's ML `tech_specs`), `ambiguous` (e.g. one number, or box/shipping size), or `missing`. Only `stated` and `inferred` can be placed, and `inferred` gets a warning badge.
- **Rotation:** try each piece in both orientations before declaring it doesn't fit.
- **Data-gap report per search:** "Of 25 desks Shopify returned, 9 list usable dimensions." That's the platform critique with real numbers, shown live in the app.
- **Done when:** tests cover each confidence class, a rotation that turns a fail into a pass, and the data-gap counts.

### M6: UCP checkout session, no purchase (~30 min, starts with the spike)
- **Scope:** `checkout.py` (`create_checkout`, `get_checkout`, `cancel_checkout`) and `POST /api/checkout/{shop_id}`, grouped by shop: one session per merchant. The UI shows the per-merchant sessions with status, totals and a "Continue on merchant site" link. It's labeled "Prototype: purchase disabled."
- **Done when:** mocked tests cover the request shape, the buyer-IP header, and grouping by merchant. The guardrail test (no `complete_checkout`) passes. A live call works locally, or the fallback is in place and documented.

### Stretch (only if Ricky asks)
None for now; see section 11 for future features.

---

## 8. PR template

```
## What this milestone does
## How to try it (commands)
## Tests added
## Reviewer subagent findings (and what I did about each)
## Decisions I need from Ricky
## Follow-ups (out of scope, not built)
```

---

## 9. Storyboard the build serves (draft, not confirmed by Ricky)
1. Enter the room (the ~200 sq ft bedroom).
2. Get a set of real products that fits, with dimensions shown.
3. Swap in a bigger desk, and the 18 in chair-clearance flag fires.
4. The data gap: "only 9 of 25 desks list usable dimensions," with confidence badges.
5. UCP checkout session per merchant, with the handoff (no purchase).

---

## 10. Future features (not in this build)
- Floor plan upload and parsing.
- Auto-layout and drag-and-drop placement.
- Color, palette and theme matching across pieces (needs real color values, which the catalog doesn't have; image similarity search is a possible route).
- "Complete this look from one shop" suggestion, for fewer checkouts and bigger merchant baskets.
- An LLM layer for messy dimension text, if pattern matching proves too weak on real data.
- Multiple rooms or a whole home.
