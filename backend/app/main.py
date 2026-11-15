import asyncio
from functools import lru_cache
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.beds import BedChoice, BedSize, label, sizes_that_fit
from app.catalog import CatalogClient, CatalogError, Product
from app.fit import Evaluation, Footprints, Zone, evaluate_layout, orient, zones_for
from app.room import NO_FIT, Rect, Room, Slot, plan_room, public_slots
from app.rules import COVERAGE_WARN
from app.search import SEARCH_LIMIT, Role, build_query

app = FastAPI(title="Room Fit")

ROLES: tuple[Role, ...] = ("bed", "desk", "desk_chair", "dresser", "nightstand")


@app.exception_handler(CatalogError)
def catalog_error(_: Request, e: CatalogError) -> JSONResponse:
    """Any catalog failure (missing credentials, network, rate limit) is a 502, never a 500."""
    return JSONResponse({"detail": f"catalog error: {e}"}, status_code=502)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@lru_cache
def get_catalog() -> CatalogClient:
    return CatalogClient.from_env()


class LayoutItem(BaseModel):
    slot_id: Role
    product: Product
    footprint_basis: Literal["parsed", "assumed"] = "parsed"


class Unplaced(BaseModel):
    slot_id: Role
    reason: str


class EvaluateRequest(BaseModel):
    room: Room
    layout: list[LayoutItem]


class EvaluateResponse(BaseModel):
    slots: list[Slot]
    placed: dict[Role, Rect]  # original room coordinates
    evaluation: Evaluation
    zones: list[Zone]  # clearance areas to shade, original room coordinates
    unplaced: list[Unplaced]


def _footprints(layout: list[LayoutItem]) -> tuple[Footprints, list[Unplaced]]:
    fp: Footprints = {}
    unplaced: list[Unplaced] = []
    seen: set[str] = set()
    for item in layout:
        if item.slot_id in seen:
            raise HTTPException(422, f"slot {item.slot_id} appears twice")
        seen.add(item.slot_id)
        if item.slot_id == "desk_chair":
            continue  # the chair footprint is assumed (rules.CHAIR_ASSUMED); it follows the desk
        if item.product.dimensions is None:
            unplaced.append(Unplaced(slot_id=item.slot_id, reason="dimensions missing"))
        else:
            fp[item.slot_id] = orient(item.product.dimensions)
    return fp, unplaced


def _evaluate(room: Room, layout: list[LayoutItem]) -> EvaluateResponse:
    fp, unplaced = _footprints(layout)
    plan, placed, ev = evaluate_layout(room, fp)
    return EvaluateResponse(
        slots=public_slots(room, plan),
        placed={r: plan.frame.rect_back(rect) for r, rect in placed.items()},
        evaluation=ev,
        zones=[
            z.model_copy(update={"rect": plan.frame.rect_back(z.rect)})
            for z in zones_for(plan, placed, ev)
        ],
        unplaced=unplaced,
    )


@app.post("/api/evaluate")
def evaluate(req: EvaluateRequest) -> EvaluateResponse:
    return _evaluate(req.room, req.layout)


class RecommendRequest(BaseModel):
    room: Room
    bed_size: BedChoice = "auto"  # auto = the biggest size that suits the room


class SearchStats(BaseModel):
    found: int
    with_dimensions: int
    fit_slot: int


class Candidate(BaseModel):
    """A searched product the UI may offer as a swap."""

    product: Product
    fits_slot: bool  # parsed dimensions that fit the slot's space (rules are checked on swap)


class RecommendResponse(EvaluateResponse):
    layout: list[LayoutItem]
    sorted_by: str = "lowest price that fits"
    searched: dict[Role, SearchStats]
    candidates: dict[Role, list[Candidate]]  # every searched product per slot, cheapest first
    bed_size: BedSize | None = None  # the size searched for the bed (None: no bed slot)
    bed_size_reason: str | None = None


def _fail_sizes(ev: Evaluation) -> dict[tuple[str, tuple[str, ...]], float]:
    return {(f.rule, tuple(f.pieces)): f.short_in for f in ev.hard_fails}


def _worse_than(
    trial: Evaluation, baseline: dict[tuple[str, tuple[str, ...]], float]
) -> bool:
    """True if the trial adds a hard fail, or makes one that already exists bigger."""
    return any(
        k not in baseline or short > baseline[k]
        for k, short in _fail_sizes(trial).items()
    )


@app.post("/api/recommend")
async def recommend(
    req: RecommendRequest, catalog: Annotated[CatalogClient, Depends(get_catalog)]
) -> RecommendResponse:
    room = req.room
    plan = plan_room(room)
    wanted: set[Role] = {"bed", *room.needs}
    if "desk" in wanted:
        wanted.add("desk_chair")
    roles = [r for r in ROLES if r != "bed" and r in wanted and plan.slots[r].fits]

    async def search(role: Role) -> list[Product]:
        sp = plan.slots[role]
        return await catalog.search(
            build_query(role, (sp.max_along, sp.max_across)), SEARCH_LIMIT
        )

    try:
        results: dict[Role, list[Product]] = dict(
            zip(roles, await asyncio.gather(*(search(r) for r in roles)), strict=True)
        )
    except CatalogError as e:
        raise HTTPException(502, f"catalog error: {e}") from None

    def cheapest_first(ps: list[Product]) -> list[Product]:
        return sorted(ps, key=lambda p: (p.price.amount, p.title, p.id))

    def fits_slot(role: Role, p: Product) -> bool:
        if role == "desk_chair":
            return True  # the chair's footprint is assumed
        sp = plan.slots[role]
        if p.dimensions is None:
            return False
        along, across = orient(p.dimensions)
        return along <= sp.max_along + 1e-9 and across <= sp.max_across + 1e-9

    fp: Footprints = {}
    chosen: list[LayoutItem] = []
    stats: dict[Role, SearchStats] = {}
    baseline = _fail_sizes(
        evaluate_layout(room, {})[2]
    )  # fails with no furniture at all

    def pick(role: Role, products: list[Product]) -> None:
        """Take the cheapest listing that fits the slot, adds no hard fail and keeps coverage ok."""
        sized = [p for p in products if p.dimensions is not None]
        fitting = [p for p in sized if fits_slot(role, p)]
        stats[role] = SearchStats(
            found=len(products), with_dimensions=len(sized), fit_slot=len(fitting)
        )
        for p in cheapest_first(fitting):
            assert p.dimensions is not None
            trial = {**fp, role: orient(p.dimensions)}
            ev = evaluate_layout(room, trial)[2]
            if not _worse_than(ev, baseline) and (
                role != "bed" or ev.coverage_pct <= COVERAGE_WARN
            ):
                fp[role] = trial[role]
                chosen.append(LayoutItem(slot_id=role, product=p))
                return

    # bed first, in the biggest size that suits the room (or the size the renter asked for)
    bed_size: BedSize | None = None
    bed_reason: str | None = None
    bed_slot = plan.slots["bed"]
    if bed_slot.fits:
        if req.bed_size == "auto":
            sizes: list[BedSize] = sizes_that_fit(
                bed_slot.max_along, bed_slot.max_across
            ) or ["twin_xl"]
        else:
            sizes = [req.bed_size]
        for size in sizes:
            found = await catalog.search(
                build_query("bed", (bed_slot.max_along, bed_slot.max_across), label(size)),
                SEARCH_LIMIT,
            )
            results["bed"] = found
            bed_size = size
            pick("bed", found)
            if "bed" in fp:
                break
        if req.bed_size != "auto":
            bed_reason = f"{label(bed_size)}: the size you chose" if bed_size else None
        elif bed_size and "bed" in fp:
            top = sizes[0]
            bed_reason = (
                f"{label(bed_size)}: the biggest size that fits this room"
                if bed_size == top
                else f"{label(bed_size)}: {label(top)} was too big for every listing found"
            )

    # desk last: the chair's 18 in behind-clearance depends on what is already placed
    for role in ("nightstand", "dresser", "desk"):
        if role in results:
            pick(role, results[role])
    if (
        "desk" in fp and "desk_chair" in results
    ):  # chair size is assumed, so any chair will do
        chairs = cheapest_first(results["desk_chair"])
        stats["desk_chair"] = SearchStats(
            found=len(chairs),
            with_dimensions=sum(c.dimensions is not None for c in chairs),
            fit_slot=len(chairs),
        )
        if chairs:
            chosen.append(
                LayoutItem(
                    slot_id="desk_chair", product=chairs[0], footprint_basis="assumed"
                )
            )
    chosen.sort(key=lambda it: ROLES.index(it.slot_id))

    def why(role: Role) -> str:
        st = stats.get(role)
        if not plan.slots[role].fits:
            return NO_FIT[role]
        if st is None or st.with_dimensions == 0:
            return "no listing with usable dimensions"
        if st.fit_slot == 0:
            return NO_FIT[role]
        return f"every {role.replace('_', ' ')} that fits breaks a rule"

    unplaceable = [
        Unplaced(slot_id=r, reason=why(r))
        for r in ROLES
        if r not in fp and r != "desk_chair" and r in wanted
    ]
    base = _evaluate(room, chosen)
    candidates = {
        r: [Candidate(product=p, fits_slot=fits_slot(r, p)) for p in cheapest_first(results.get(r, []))]
        for r in ROLES
    }
    return RecommendResponse(
        **base.model_dump(exclude={"unplaced"}),
        unplaced=unplaceable,
        layout=chosen,
        searched=stats,
        candidates=candidates,
        bed_size=bed_size,
        bed_size_reason=bed_reason,
    )
