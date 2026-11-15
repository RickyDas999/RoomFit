import asyncio
from functools import lru_cache
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from app.catalog import CatalogClient, CatalogError, Product
from app.fit import Evaluation, Footprints, evaluate_layout, orient
from app.room import NO_FIT, Rect, Room, Slot, plan_room, public_slots
from app.search import SEARCH_LIMIT, Role, build_query

app = FastAPI(title="Room Fit")

ROLES: tuple[Role, ...] = ("bed", "desk", "desk_chair", "dresser", "nightstand")


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
    unplaced: list[Unplaced]


def _footprints(layout: list[LayoutItem]) -> tuple[Footprints, list[Unplaced]]:
    fp: Footprints = {}
    unplaced: list[Unplaced] = []
    for item in layout:
        if item.slot_id in fp or any(u.slot_id == item.slot_id for u in unplaced):
            raise HTTPException(422, f"slot {item.slot_id} appears twice")
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
        unplaced=unplaced,
    )


@app.post("/api/evaluate")
def evaluate(req: EvaluateRequest) -> EvaluateResponse:
    return _evaluate(req.room, req.layout)


class RecommendRequest(BaseModel):
    room: Room


class SearchStats(BaseModel):
    found: int
    with_dimensions: int
    fit_slot: int


class RecommendResponse(EvaluateResponse):
    layout: list[LayoutItem]
    sorted_by: str = "lowest price that fits"
    searched: dict[Role, SearchStats]


def _rule_keys(ev: Evaluation) -> set[tuple[str, tuple[str, ...]]]:
    return {(f.rule, tuple(f.pieces)) for f in ev.hard_fails}


@app.post("/api/recommend")
async def recommend(
    req: RecommendRequest, catalog: Annotated[CatalogClient, Depends(get_catalog)]
) -> RecommendResponse:
    room = req.room
    plan = plan_room(room)
    roles = [r for r in ROLES if plan.slots[r].fits]

    async def search(role: Role) -> list[Product]:
        sp = plan.slots[role]
        return await catalog.search(
            build_query(role, (sp.max_along, sp.max_across)), SEARCH_LIMIT
        )

    try:
        results = dict(
            zip(roles, await asyncio.gather(*(search(r) for r in roles)), strict=True)
        )
    except CatalogError as e:
        raise HTTPException(502, f"catalog error: {e}") from None

    def cheapest_first(ps: list[Product]) -> list[Product]:
        return sorted(ps, key=lambda p: (p.price.amount, p.title))

    fp: Footprints = {}
    chosen: list[LayoutItem] = []
    stats: dict[Role, SearchStats] = {}
    baseline = _rule_keys(
        evaluate_layout(room, {})[2]
    )  # fails that exist with no furniture at all
    # desk last: the chair's 18 in behind-clearance depends on what is already placed
    for role in ("bed", "nightstand", "dresser", "desk"):
        if role not in results:
            continue
        sp = plan.slots[role]
        sized = [p for p in results[role] if p.dimensions is not None]
        fitting = [
            p
            for p in sized
            if p.dimensions
            and orient(p.dimensions)[0] <= sp.max_along + 1e-9
            and orient(p.dimensions)[1] <= sp.max_across + 1e-9
        ]
        stats[role] = SearchStats(
            found=len(results[role]), with_dimensions=len(sized), fit_slot=len(fitting)
        )
        for p in cheapest_first(fitting):
            assert p.dimensions is not None
            trial = {**fp, role: orient(p.dimensions)}
            if not _rule_keys(evaluate_layout(room, trial)[2]) - baseline:
                fp[role] = trial[role]
                chosen.append(LayoutItem(slot_id=role, product=p))
                break
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
        if r not in fp and r != "desk_chair"
    ]
    base = _evaluate(room, chosen)
    return RecommendResponse(
        **base.model_dump(exclude={"unplaced"}),
        unplaced=unplaceable,
        layout=chosen,
        searched=stats,
    )
