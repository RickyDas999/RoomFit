import asyncio
from collections import Counter
from functools import lru_cache
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.beds import BedChoice, BedSize, label, matches_size, sizes_that_fit
from app.cart import MAX_SHOPS, CartClient, CartSession, create_carts
from app.catalog import CatalogClient, CatalogError, Product, Shop
from app.fit import (
    Evaluation,
    Footprints,
    Zone,
    evaluate_layout,
    orient,
    orientations,
    zones_for,
)
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
    # None: the engine tries both ways and keeps the better one. True: turned 90 degrees
    # (short side along the wall). False: long side along the wall.
    rotated: bool | None = None


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
    rotated: list[Role] = []  # pieces placed turned 90 degrees (short side along the wall)


ORDER: tuple[Role, ...] = ("bed", "nightstand", "dresser", "desk")  # desk last (chair clearance)


def _score(ev: Evaluation) -> tuple[int, float]:
    return len(ev.hard_fails), sum(f.short_in for f in ev.hard_fails)


def _footprints(
    room: Room, layout: list[LayoutItem]
) -> tuple[Footprints, list[Role], list[Unplaced]]:
    """Footprints for the layout. A piece with no chosen orientation gets the better of both."""
    by_role: dict[Role, LayoutItem] = {}
    unplaced: list[Unplaced] = []
    for item in layout:
        if item.slot_id in by_role:
            raise HTTPException(422, f"slot {item.slot_id} appears twice")
        by_role[item.slot_id] = item
    fp: Footprints = {}
    rotated: list[Role] = []
    for role in ORDER:
        chosen_item = by_role.get(role)
        if chosen_item is None:
            continue
        dims = chosen_item.product.dimensions
        if dims is None:
            unplaced.append(Unplaced(slot_id=role, reason="dimensions missing"))
            continue
        options = orientations(dims)
        if chosen_item.rotated is not None:
            options = [options[-1] if chosen_item.rotated else options[0]]
        best = min(options, key=lambda o: _score(evaluate_layout(room, {**fp, role: o})[2]))
        fp[role] = best
        if best != orient(dims):
            rotated.append(role)
    # the chair's footprint is assumed (rules.CHAIR_ASSUMED); it follows the desk
    return fp, rotated, unplaced


def _evaluate(room: Room, layout: list[LayoutItem]) -> EvaluateResponse:
    fp, rotated, unplaced = _footprints(room, layout)
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
        rotated=rotated,
    )


@app.post("/api/evaluate")
def evaluate(req: EvaluateRequest) -> EvaluateResponse:
    return _evaluate(req.room, req.layout)


class RecommendRequest(BaseModel):
    room: Room
    bed_size: BedChoice = "auto"  # auto = the biggest size that suits the room


class SearchStats(BaseModel):
    found: int
    with_dimensions: int  # usable: stated + inferred
    fit_slot: int
    stated: int = 0
    inferred: int = 0
    ambiguous: int = 0
    missing: int = 0


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
        return any(
            along <= sp.max_along + 1e-9 and across <= sp.max_across + 1e-9
            for along, across in orientations(p.dimensions)
        )

    fp: Footprints = {}
    chosen: list[LayoutItem] = []
    stats: dict[Role, SearchStats] = {}
    baseline = _fail_sizes(
        evaluate_layout(room, {})[2]
    )  # fails with no furniture at all

    def pick(role: Role, products: list[Product], size: BedSize | None = None) -> None:
        """Take the cheapest listing that fits the slot, adds no hard fail and keeps coverage ok."""
        sized = [p for p in products if p.dimensions is not None]
        fitting = [p for p in sized if fits_slot(role, p)]
        if size is not None:  # a bed listing must really be that size
            fitting = [
                p for p in fitting if p.dimensions and matches_size(size, *orient(p.dimensions))
            ]
        count = Counter(p.dimension_confidence for p in products)
        stats[role] = SearchStats(
            found=len(products),
            with_dimensions=len(sized),
            fit_slot=len(fitting),
            stated=count["stated"],
            inferred=count["inferred"],
            ambiguous=count["ambiguous"],
            missing=count["missing"],
        )
        sp = plan.slots[role]
        for p in cheapest_first(fitting):
            assert p.dimensions is not None
            for along, across in orientations(p.dimensions):  # long side along the wall first
                if along > sp.max_along + 1e-9 or across > sp.max_across + 1e-9:
                    continue
                trial = {**fp, role: (along, across)}
                ev = evaluate_layout(room, trial)[2]
                if not _worse_than(ev, baseline) and (
                    role != "bed" or ev.coverage_pct <= COVERAGE_WARN
                ):
                    fp[role] = trial[role]
                    chosen.append(
                        LayoutItem(
                            slot_id=role,
                            product=p,
                            rotated=(along, across) != orient(p.dimensions),
                        )
                    )
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
            pick("bed", found, size)
            if "bed" in fp:
                break
        if "bed" not in fp or bed_size is None:
            bed_size = None  # nothing was placed, so there is no size to report
        elif req.bed_size != "auto":
            bed_reason = f"{label(bed_size)}: the size you chose"
        elif bed_size:
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
        return f"every {role.replace('_', ' ')} that fits breaks a rule or leaves too little floor"

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


# --- carts per merchant (the checkout step; no purchase, see app/cart.py) ---


@lru_cache
def get_cart_client() -> CartClient:
    return CartClient.from_env()


class CheckoutRequest(BaseModel):
    layout: list[LayoutItem] = Field(max_length=20)  # the room has five slots; no way to inflate a cart


class CheckoutResponse(BaseModel):
    sessions: list[CartSession]  # one per merchant
    notice: str = "Prototype: purchase disabled"


@app.post("/api/checkout")
async def checkout(
    req: CheckoutRequest, carts: Annotated[CartClient, Depends(get_cart_client)]
) -> CheckoutResponse:
    """One cart per merchant for the chosen products (quantity 1 each). Nothing is bought."""
    groups: dict[str, tuple[Shop, dict[str, int]]] = {}
    for item in req.layout:
        shop = item.product.shop.model_copy(
            update={"domain": item.product.shop.domain.strip().lower()}
        )
        _, variants = groups.setdefault(shop.domain, (shop, {}))
        variants[item.product.variant_id] = variants.get(item.product.variant_id, 0) + 1
    if len(groups) > MAX_SHOPS:
        raise HTTPException(422, f"at most {MAX_SHOPS} merchants at a time")
    return CheckoutResponse(sessions=await create_carts(carts, groups))


class CartRef(BaseModel):
    domain: str
    cart_id: str


class CancelRequest(BaseModel):
    carts: list[CartRef] = Field(max_length=MAX_SHOPS)


class CancelResponse(BaseModel):
    cancelled: int
    failed: int


@app.post("/api/checkout/cancel")
async def cancel_checkout(
    req: CancelRequest, carts: Annotated[CartClient, Depends(get_cart_client)]
) -> CancelResponse:
    """Cancel carts made by /api/checkout (manual button, room change, page close)."""
    done = await asyncio.gather(
        *(carts.cancel(c.domain.strip().lower(), c.cart_id) for c in req.carts)
    )
    return CancelResponse(cancelled=sum(done), failed=len(done) - sum(done))
