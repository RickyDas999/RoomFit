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
| 2026-11-15 | M1: search query wording per role is a placeholder taken from the handoff examples; M3 refines it. | Ricky (approved as-is until refined) |
| 2026-11-15 | M1: catalog client skips malformed products instead of failing the search; `Retry-After` is capped at 30 s; concurrent searches share one token fetch. | Claude, from M1 review |
| 2026-11-15 | M1: only `variants[0]`-style first usable variant is used per product for now; M3 may need all variants for "cheapest that fits". | Claude (to revisit in M3) |
| 2026-11-15 | M1: our profile URL only works after M1 merges to `main` (raw GitHub URL). Until then the live dev script gets HTTP 422 `profile_unreachable`. | Claude |
| 2026-11-15 | M2: ambiguous listings (several different sizes, shipping/box size, mattress size, component-only, range, partial) return `dimensions = null` plus a structured result: `status` (`parsed`/`ambiguous`/`missing`), `reason`, and `candidates` for multiple sizes. Nothing is guessed. | Ricky |
| 2026-11-15 | M2: dimensions are always normalized to W x D x H. Unlabeled numbers are read as W x D x H; labels override position. `L` fills whichever of W/D is not stated (explicit W wins, so `L x W x H` gives d = L). | Ricky (W x D x H); L rule is Claude's default |
| 2026-11-15 | M2: width and depth are required; height is optional (many listings give only W x D). Value cap 300 in as a sanity guard. | Claude (matches plan Ricky approved) |
| 2026-11-15 | M2: a listing that repeats the same size (e.g. Twin and Twin XL with identical numbers) counts as parsed; "Overall ..." beats component sizes like "Drawer ...". | Claude (to confirm) |
| 2026-11-15 | M2: `Product.dimension_status` and `dimension_reason` added next to `dimensions`/`dimension_source`, so M5's confidence classes can build on them. `metadata.tech_specs` is not read until M5. | Claude |
| 2026-11-15 | M2: the same size stated twice (inches and cm) counts as one size, tolerance 1 in. 4+ numbers in a row is ambiguous (`too_many_values`); a quantity prefix ("Qty 2 x 18 in", "Pack of 4 x ...") is ambiguous (`quantity`). Fractions (`39 1/2"`) and feet+inches (`6'2"`) are read as real values. | Claude, from M2 test-writer/reviewer (to confirm) |
| 2026-11-15 | M2: width and depth must be at least 6 in (`MIN_INCHES`), at most 300 in; smaller is ambiguous (`implausible`). | Ricky |
| 2026-11-15 | M2: Ricky accepted the parser defaults (repeated identical size = parsed; "Overall" beats component sizes; 1 in tolerance for in/cm duplicates; `L` fills the missing W/D, explicit W wins). | Ricky |
| 2026-11-15 | Serve the agent profile via jsDelivr (`cdn.jsdelivr.net/gh/RickyDas999/RoomFit@main/agent-profile/ucp-profile.json`) instead of raw GitHub: Shopify rejects raw GitHub (`profile_malformed: Invalid content type`, it serves `text/plain`). Note: jsDelivr caches `@main`, so profile edits can take a while to appear (purge at `purge.jsdelivr.net` if needed). | Ricky (jsDelivr, separate PR) |
| 2026-11-15 | M3: the 36 in door path runs from the door to the room's center line (depth / 2), not to the opposite wall. | Ricky |
| 2026-11-15 | M3: desk chair footprint is a fixed, labeled assumption of 20 x 20 in (`rules.CHAIR_ASSUMED`), because 0 of 25 live chair listings had parseable dimensions. | Ricky |
| 2026-11-15 | M3: sample room is 144 x 192 in; door 32 in wide centered on the top wall; window 48 in centered on the bottom wall; closet 48 x 24 in in the top-left corner. | Ricky |
| 2026-11-15 | M3: coverage = furniture footprint / full room area (closet not subtracted). Verdict: any hard fail = `cramped`; else missing need = `incomplete`; else coverage over 40% = `cramped`; else `fits`. Warn above 40%, flag above 45%. | Ricky |
| 2026-11-15 | M3: door swing is not enforced as a rule (it is drawn in M4). | Ricky |
| 2026-11-15 | M3: one PR (not split into geometry and recommend). | Claude (Ricky did not answer the split question); confirmed by Ricky |
| 2026-11-15 | M3: a nightstand beside the bed head does not count as blocking the bed's 24 in open side; one open long side is enough (twin may sit against a wall). | Claude (to confirm); confirmed by Ricky |
| 2026-11-15 | M3: two checks beyond the rules table, needed for correctness: pieces must not overlap each other or the closet, and must stay inside the room (both hard fails). | Claude (to confirm); confirmed by Ricky |
| 2026-11-15 | M3: furniture is oriented with its longer side along the wall (bed, desk, dresser, nightstand). A desk listed 48 x 54 is 54 long and 48 deep. Rotation (trying both) comes in M5. | Claude (to confirm); confirmed by Ricky |
| 2026-11-15 | M3: layout recipe (door on top wall; any room is flipped into this frame): bed in the far corner on the wider side of the lane, head at the far wall; nightstand beside the bed head; dresser on the door wall on the bed's side; desk in the far corner on the other side, long side on the side wall, chair pulled out in front and centered. The door lane may be overlapped by clearance zones (empty space) but not by furniture. | Claude (to confirm; ASCII sketch in the PR); confirmed by Ricky |
| 2026-11-15 | M3: `/api/recommend` chooses in the order bed, nightstand, dresser, desk (desk last, because the chair's 18 in behind-clearance depends on what is already placed), taking the cheapest listing with parsed dimensions that fits the slot and adds no new hard fail. | Claude (to confirm); confirmed by Ricky |
| 2026-11-15 | M3: the chair is searched and the cheapest chair is shown, but its footprint is always the assumed 20 x 20 in (labeled `footprint_basis: "assumed"`); `/api/evaluate` ignores a chair product's real size. | Claude, extends Ricky's chair decision (to confirm); confirmed by Ricky |
| 2026-11-15 | M3: search wording gets a size hint capped at 60 in for desks and 48 in for dressers (`search.QUERY_SIZE_CAP`), so a 96 in slot does not search "desk 96 inch". Search hint only, not a fit rule. | Claude (to confirm); confirmed by Ricky |
| 2026-11-15 | M3 known limits: a closet in the dresser's or desk's own corner shrinks that slot (or removes it) instead of moving the anchor; the door lane is ignored at the side where a corner door pushes it against a wall (lane is clamped inside the room). | Claude; confirmed by Ricky |
| 2026-11-15 | M3: when a door is wider than 36 in, the lane is as wide as the door (an extra, not a rule value); doors at 36 in or less use 36 in. | Claude (to confirm); confirmed by Ricky |
| 2026-11-15 | M3: closet front = the side away from its wall; a tall closet (deeper than wide) in a corner is read as a side-wall closet and faces left/right. | Claude, from M3 review; confirmed by Ricky |
| 2026-11-15 | M3: any catalog failure (missing credentials, network error, rate limit) returns HTTP 502 from `/api/recommend`, never a 500. `Dimensions` width and depth must be greater than 0 (API returns 422 otherwise). Price ties break by title, then product id. | Claude, from M3 review; confirmed by Ricky |
| 2026-11-15 | M3: `/api/recommend` rejects a candidate that adds a hard fail OR makes an existing one (for example a closet already in the lane) bigger. | Claude, from M3 review; confirmed by Ricky |
| 2026-11-15 | M3: Ricky signed off on the default layout sketch and on all M3 design choices above; demo plan is to use a deep corner desk for the chair-clearance moment. | Ricky |
