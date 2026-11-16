"""Adversarial M3 tests: random rooms, symmetry, degenerate numbers, recommend edge cases.

Synthetic data only; the catalog is a fake (no network).
"""

import random
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.catalog import Price, Product, Shop
from app.dimensions import Dimensions
from app.fit import Evaluation, Footprints, evaluate_layout, verdict_for
from app.main import app, get_catalog
from app.room import Door, Rect, Room, Wall, Window, plan_room, public_slots
from app.search import Role

WALLS: list[Wall] = ["top", "bottom", "left", "right"]
ROLES: tuple[Role, ...] = ("bed", "desk", "desk_chair", "dresser", "nightstand")
client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    yield
    app.dependency_overrides.clear()


# ---------- helpers ----------


def random_room(rng: random.Random) -> Room:
    w, d = rng.randint(60, 300), rng.randint(60, 300)
    wall = rng.choice(WALLS)
    length = w if wall in ("top", "bottom") else d
    dw = min(rng.choice([24, 30, 32, 36, 40, 48, 60]), length)
    offset = rng.choice([0, length - dw, rng.randint(0, length - dw)])
    window = None
    if rng.random() < 0.5:
        ww = rng.choice(WALLS)
        wl = w if ww in ("top", "bottom") else d
        win_w = min(40, wl)
        window = Window(wall=ww, offset=rng.randint(0, int(wl - win_w)), width=win_w)
    closet = None
    if rng.random() < 0.8:
        cw, cd = rng.randint(20, min(60, w)), rng.randint(20, min(40, d))
        kind = rng.choice(["corner", "wall", "free"])
        cx = rng.choice([0, w - cw]) if kind == "corner" else rng.randint(0, w - cw)
        cy = rng.choice([0, d - cd]) if kind == "corner" else rng.randint(0, d - cd)
        if kind == "wall":
            if rng.random() < 0.5:
                cy = rng.choice([0, d - cd])
            else:
                cx = rng.choice([0, w - cw])
        closet = Rect(x=cx, y=cy, w=cw, d=cd)
    return Room(
        width=w,
        depth=d,
        door=Door(wall=wall, offset=offset, width=dw),
        window=window,
        closet=closet,
    )


def rooms(n: int = 300, seed: int = 7) -> list[Room]:
    rng = random.Random(seed)
    return [random_room(rng) for _ in range(n)]


def random_footprints(rng: random.Random, room: Room) -> Footprints:
    plan = plan_room(room)
    fp: Footprints = {}
    for role in ("bed", "desk", "dresser", "nightstand"):
        sp = plan.slots[role]
        if sp.fits and rng.random() < 0.8:
            fp[role] = (
                max(
                    20.0, sp.max_along * rng.uniform(0.3, 1.0)
                ),  # desk: long side >= chair
                max(6.0, sp.max_across * rng.uniform(0.3, 1.0)),
            )
    return {
        r: v
        for r, v in fp.items()
        if v[0] <= plan.slots[r].max_along + 1e-9
        and v[1] <= plan.slots[r].max_across + 1e-9
    }


NEXT: dict[str, Wall] = {
    "top": "right",
    "right": "bottom",
    "bottom": "left",
    "left": "top",
}


def rotate(room: Room, k: int, mirror: bool) -> Room:
    """Rotate the whole room by k quarter turns clockwise, optionally mirrored left-right first."""
    w, d = room.width, room.depth
    door, win, closet = room.door, room.window, room.closet
    if mirror:
        flip: dict[str, Wall] = {
            "top": "top",
            "bottom": "bottom",
            "left": "right",
            "right": "left",
        }

        def mw(x: Door | Window) -> tuple[Wall, float]:
            off = x.offset if x.wall in ("left", "right") else w - x.offset - x.width
            return flip[x.wall], off

        dw, do = mw(door)
        door = Door(wall=dw, offset=do, width=door.width)
        if win:
            ww, wo = mw(win)
            win = Window(wall=ww, offset=wo, width=win.width)
        if closet:
            closet = Rect(x=w - closet.x2, y=closet.y, w=closet.w, d=closet.d)
    for _ in range(k):

        def rot(
            x: Door | Window, depth: float = d, nxt: dict[str, Wall] = NEXT
        ) -> tuple[Wall, float]:
            off = (
                depth - x.offset - x.width if x.wall in ("right", "left") else x.offset
            )
            return nxt[x.wall], off

        a, b = rot(door)
        door = Door(wall=a, offset=b, width=door.width)
        if win:
            a, b = rot(win)
            win = Window(wall=a, offset=b, width=win.width)
        if closet:
            closet = Rect(x=d - closet.y2, y=closet.x, w=closet.d, d=closet.w)
        w, d = d, w
    return Room(width=w, depth=d, door=door, window=win, closet=closet)


def sig(ev: Evaluation) -> tuple[object, ...]:
    return (
        sorted((f.rule, tuple(f.pieces), f.short_in) for f in ev.hard_fails),
        ev.coverage_pct,
        ev.missing_needs,
        ev.verdict,
    )


def inside(r: Rect, w: float, d: float) -> bool:
    return r.x >= -1e-6 and r.y >= -1e-6 and r.x2 <= w + 1e-6 and r.y2 <= d + 1e-6


# ---------- planning properties ----------


def test_plan_and_evaluate_never_raise_on_random_rooms() -> None:
    rng = random.Random(1)
    for room in rooms():
        plan = plan_room(room)
        public_slots(room, plan)
        evaluate_layout(room, random_footprints(rng, room))
        evaluate_layout(room, {})


def test_slot_regions_stay_inside_room_and_clear_of_lane_and_closet() -> None:
    for room in rooms():
        plan = plan_room(room)
        assert inside(plan.lane, plan.W, plan.D), room
        for role, sp in plan.slots.items():
            if sp.region.area <= 0:
                continue
            assert inside(sp.region, plan.W, plan.D), (role, room)
            assert not sp.region.intersects(plan.lane), (
                role,
                room,
                sp.region,
                plan.lane,
            )
            for obst in (plan.closet, plan.closet_front):
                if obst:
                    assert not sp.region.intersects(obst), (role, room)


def test_public_slot_regions_are_in_original_coordinates() -> None:
    for room in rooms():
        for s in public_slots(room):
            if s.region.area > 0:
                assert inside(s.region, room.width, room.depth), (s.role, room)


def test_placed_pieces_back_in_original_room_and_no_outside_room_fail() -> None:
    rng = random.Random(2)
    for room in rooms():
        fp = random_footprints(rng, room)
        plan, placed, ev = evaluate_layout(room, fp)
        assert not [f for f in ev.hard_fails if f.rule == "outside_room"], (room, fp)
        for role, r in placed.items():
            assert inside(plan.frame.rect_back(r), room.width, room.depth), (role, room)


@pytest.mark.parametrize(
    "k,mirror",
    [(1, False), (2, False), (3, False), (0, True), (1, True), (2, True), (3, True)],
)
def test_rotating_or_mirroring_whole_room_gives_same_evaluation(
    k: int, mirror: bool
) -> None:
    rng = random.Random(3)
    checked = 0
    for room in rooms(200):
        plan = plan_room(room)
        if abs(plan.lane.x - (plan.W - plan.lane.x2)) < 1e-6:
            continue  # symmetric lane: bed side is a tie-break, so mirrored layouts may differ
        fp = random_footprints(rng, room)
        other = rotate(room, k, mirror)
        assert sig(evaluate_layout(room, fp)[2]) == sig(
            evaluate_layout(other, fp)[2]
        ), (room, other, fp)
        checked += 1
    assert checked > 50


def test_evaluating_same_layout_twice_is_identical() -> None:
    rng = random.Random(4)
    for room in rooms(100):
        fp = random_footprints(rng, room)
        a, b = evaluate_layout(room, fp), evaluate_layout(room, fp)
        assert a[2] == b[2] and a[1] == b[1]


def test_coverage_matches_sum_of_placed_areas() -> None:
    rng = random.Random(5)
    for room in rooms(100):
        fp = random_footprints(rng, room)
        _, placed, ev = evaluate_layout(room, fp)
        expected = (
            sum(r.w * r.d for r in placed.values()) / (room.width * room.depth) * 100
        )
        assert ev.coverage_pct == pytest.approx(expected, abs=0.006)


def test_coverage_status_matches_thresholds() -> None:
    rng = random.Random(6)
    for room in rooms(100):
        ev = evaluate_layout(room, random_footprints(rng, room))[2]
        want = (
            "flag" if ev.coverage_pct > 45 else "warn" if ev.coverage_pct > 40 else "ok"
        )
        assert ev.coverage_status == want


# ---------- verdict ----------


@pytest.mark.parametrize(
    "fail,missing,cov,want",
    [
        (True, ["sleep"], 99.0, "cramped"),  # hard fail beats missing
        (False, ["sleep"], 99.0, "incomplete"),  # missing beats coverage
        (False, [], 40.0, "fits"),  # exactly 40 is not "over"
        (False, [], 40.01, "cramped"),
        (False, [], 0.0, "fits"),
    ],
)
def test_verdict_precedence(
    fail: bool, missing: list[str], cov: float, want: str
) -> None:
    assert verdict_for(fail, missing, cov) == want


def test_verdict_uses_unrounded_coverage_boundary() -> None:
    # 40.004% rounds to 40.0 in the response but is over the line: verdict and status must agree.
    room = Room(width=100, depth=100, door=Door(wall="top", offset=30, width=36))
    ev = evaluate_layout(room, {"bed": (100.0, 40.004 / 1.0)})[2]
    assert ev.coverage_pct == 40.0
    assert (ev.coverage_status == "warn") == (
        ev.verdict == "cramped" or bool(ev.hard_fails)
    )


# ---------- degenerate footprints and rooms ----------


@pytest.mark.parametrize(
    "fp", [(0.0, 0.0), (-5.0, 10.0), (-5.0, -5.0), (1e9, 1e9), (1e-12, 1e-12)]
)
@pytest.mark.parametrize("role", ["bed", "desk", "dresser", "nightstand"])
def test_weird_footprints_do_not_raise_and_coverage_is_sane(
    role: Role, fp: tuple[float, float]
) -> None:
    ev = evaluate_layout(
        Room(width=144, depth=192, door=Door(wall="top", offset=56, width=32)),
        {role: fp},
    )[2]
    assert 0 <= ev.coverage_pct <= 1e30
    assert ev.verdict in ("fits", "cramped", "incomplete")


def test_zero_size_piece_is_not_a_hard_fail() -> None:
    room = Room(width=144, depth=192, door=Door(wall="top", offset=56, width=32))
    ev = evaluate_layout(room, {"dresser": (0.0, 0.0)})[2]
    assert not ev.hard_fails or ev.hard_fails[0].rule == "in_front_of_dresser"


def test_huge_footprint_is_hard_fail_not_crash() -> None:
    room = Room(width=144, depth=192, door=Door(wall="top", offset=56, width=32))
    ev = evaluate_layout(room, {"bed": (1e6, 1e6)})[2]
    assert any(f.rule == "outside_room" for f in ev.hard_fails)
    assert ev.verdict == "cramped"


@pytest.mark.parametrize(
    "w,d", [(1, 1), (10, 10), (36, 36), (40, 1000), (5000, 5000), (0.5, 300)]
)
@pytest.mark.parametrize("wall", ["top", "bottom", "left", "right"])
def test_tiny_and_huge_rooms(w: float, d: float, wall: Wall) -> None:
    length = w if wall in ("top", "bottom") else d
    room = Room(width=w, depth=d, door=Door(wall=wall, offset=0, width=min(30, length)))
    plan = plan_room(room)
    for sp in plan.slots.values():
        assert sp.max_along >= 0 and sp.max_across >= 0
    ev = evaluate_layout(room, {})[2]
    assert ev.verdict == "incomplete"


def test_door_wider_than_36_widens_lane_and_slots_avoid_it() -> None:
    room = Room(width=200, depth=200, door=Door(wall="top", offset=20, width=60))
    plan = plan_room(room)
    assert plan.lane.w == 60
    for sp in plan.slots.values():
        assert not sp.region.intersects(plan.lane), sp


def test_door_exactly_room_width_and_wider_than_room() -> None:
    room = Room(width=40, depth=120, door=Door(wall="top", offset=0, width=40))
    plan = plan_room(room)
    assert plan.lane.w == 40
    with pytest.raises(ValueError):
        Room(width=40, depth=120, door=Door(wall="top", offset=0, width=41))


@pytest.mark.parametrize("wall", ["top", "bottom", "left", "right"])
def test_door_near_both_corners_each_wall(wall: Wall) -> None:
    for end in (0, 1):
        length = 144 if wall in ("top", "bottom") else 192
        off = 0 if end == 0 else length - 32
        room = Room(
            width=144,
            depth=192,
            door=Door(wall=wall, offset=off, width=32),
            closet=Rect(x=0, y=0, w=48, d=24),
        )
        evaluate_layout(room, {"bed": (80, 40), "desk": (48, 24), "dresser": (36, 20)})


def test_closet_touching_lane_blocks_lane_or_is_reported() -> None:
    # closet sits across the lane at the top wall: closet overlapping the lane is a path fail
    room = Room(
        width=144,
        depth=192,
        door=Door(wall="top", offset=56, width=32),
        closet=Rect(x=40, y=0, w=60, d=24),
    )
    ev = evaluate_layout(room, {})[2]
    assert any(
        f.rule == "path_from_door" and f.pieces == ["closet"] for f in ev.hard_fails
    )


def test_closet_on_bed_side_shrinks_bed_slot_not_overlapping() -> None:
    room = Room(
        width=144,
        depth=192,
        door=Door(wall="top", offset=56, width=32),
        closet=Rect(x=96, y=168, w=48, d=24),
    )
    plan = plan_room(room)
    # the closet takes the right-hand bed corner, so the planner moves the bed to the left
    assert plan.bed_side == "left"
    assert plan.notes and "bed" in plan.notes
    bed = plan.slots["bed"]
    assert plan.closet and not bed.region.intersects(plan.closet)
    ev = evaluate_layout(room, {"bed": (bed.max_along, bed.max_across)})[2]
    assert not [f for f in ev.hard_fails if f.rule in ("overlap", "outside_room")]


def test_no_closet_no_dresser_reports_storage_missing_and_closet_absent() -> None:
    room = Room(width=144, depth=192, door=Door(wall="top", offset=56, width=32))
    ev = evaluate_layout(room, {"bed": (80, 40), "desk": (48, 24)})[2]
    assert ev.missing_needs == ["storage"]
    assert ev.verdict == "incomplete"


# ---------- API: evaluate with weird products ----------


def prod(
    pid: str, price: int, dims: tuple[float, float] | None, title: str | None = None
) -> Product:
    return Product(
        id=f"gid://shopify/p/{pid}",
        variant_id=f"gid://shopify/ProductVariant/{pid}",
        title=title if title is not None else f"item {pid}",
        shop=Shop(id="s", name="s", domain="s.example"),
        price=Price(amount=price, currency="USD"),
        image_url=None,
        url=None,
        native_checkout=True,
        description="",
        dimensions=Dimensions(w=dims[0], d=dims[1]) if dims else None,
        dimension_status="parsed" if dims else "missing",
        dimension_confidence="stated" if dims else "missing",
    )


class Fake:
    def __init__(
        self,
        by_query: dict[str, list[Product]] | None = None,
        default: list[Product] | None = None,
    ) -> None:
        self.by_query, self.default = by_query or {}, default or []

    async def search(self, query: str, limit: int = 25) -> list[Product]:
        for key, items in self.by_query.items():
            if key in query:
                return items
        return self.default


def use(fake: Fake) -> None:
    app.dependency_overrides[get_catalog] = lambda: fake


ROOM = {
    "width": 144,
    "depth": 192,
    "door": {"wall": "top", "offset": 56, "width": 32},
    "window": {"wall": "bottom", "offset": 48, "width": 48},
    "closet": {"x": 0, "y": 0, "w": 48, "d": 24},
}


def raw_item(slot: str, w: float, d: float) -> dict[str, object]:
    """A layout item as raw JSON, so non-positive sizes reach the API instead of the model."""
    item = prod(slot, 1, (40, 40)).model_dump()
    item["dimensions"] = {"w": w, "d": d, "h": None}
    return {"slot_id": slot, "product": item}


@pytest.mark.parametrize("dims", [(0, 0), (-80, 40), (40, -1)])
def test_api_evaluate_rejects_non_positive_dimensions(dims: tuple[float, float]) -> None:
    r = client.post("/api/evaluate", json={"room": ROOM, "layout": [raw_item("bed", *dims)]})
    assert r.status_code == 422


def test_api_evaluate_survives_huge_dimensions() -> None:
    r = client.post("/api/evaluate", json={"room": ROOM, "layout": [raw_item("bed", 1e7, 1e7)]})
    assert r.status_code == 200, r.text
    ev = r.json()["evaluation"]
    assert ev["verdict"] == "cramped" and ev["hard_fails"]  # far bigger than the room


# ---------- API: recommend ----------


def test_recommend_deterministic_with_duplicate_prices() -> None:
    beds = [prod(f"b{i}", 100, (80, 40), title=f"bed {c}") for i, c in enumerate("cab")]
    results = []
    for order in (beds, beds[::-1], beds[1:] + beds[:1]):
        use(Fake({"bed": order}))
        body = client.post("/api/recommend", json={"room": ROOM}).json()
        results.append([(i["slot_id"], i["product"]["id"]) for i in body["layout"]])
    assert results[0] == results[1] == results[2]


def test_recommend_all_candidates_missing_dimensions() -> None:
    use(Fake(default=[prod("x", 5, None), prod("y", 6, None)]))
    r = client.post("/api/recommend", json={"room": ROOM})
    assert r.status_code == 200
    body = r.json()
    assert body["layout"] == [] and body["placed"] == {}
    assert body["evaluation"]["verdict"] == "incomplete"
    assert {u["slot_id"] for u in body["unplaced"]} == {
        "bed",
        "desk",
        "dresser",
        "nightstand",
    }
    assert all(
        u["reason"] == "no listing with usable dimensions" for u in body["unplaced"]
    )


def test_recommend_empty_catalog() -> None:
    use(Fake())
    r = client.post("/api/recommend", json={"room": ROOM})
    assert r.status_code == 200
    assert r.json()["layout"] == []


def test_recommend_same_product_for_unrelated_queries_is_still_consistent() -> None:
    lamp = prod("lamp", 5, (10, 10), title="lamp")
    use(Fake(default=[lamp]))
    body = client.post("/api/recommend", json={"room": ROOM}).json()
    assert body["evaluation"]["hard_fails"] == []
    # every chosen product must be reported as placed
    assert {i["slot_id"] for i in body["layout"]} == set(body["placed"])


def test_recommend_result_evaluates_to_same_thing_via_evaluate() -> None:
    use(
        Fake(
            {
                "bed": [prod("b", 100, (80, 40))],
                "desk": [prod("d", 50, (48, 24))],
                "chair": [prod("c", 20, None)],
                "dresser": [prod("r", 30, (36, 20))],
                "nightstand": [prod("n", 10, (18, 16))],
            }
        )
    )
    rec = client.post("/api/recommend", json={"room": ROOM}).json()
    ev = client.post(
        "/api/evaluate", json={"room": ROOM, "layout": rec["layout"]}
    ).json()
    assert ev["evaluation"] == rec["evaluation"]
    assert ev["placed"] == rec["placed"]


def test_recommend_desk_that_fits_slot_but_conflicts_with_chosen_nightstand() -> None:
    use(
        Fake(
            {
                "bed": [prod("b", 100, (80, 40))],
                "nightstand": [prod("n", 10, (36, 30))],
                "desk": [
                    prod("big", 10, (60, 52), title="big"),  # cheapest, fills the slot
                    prod("small", 90, (48, 24), title="small"),
                ],
                "chair": [prod("c", 20, None)],
            }
        )
    )
    body = client.post("/api/recommend", json={"room": ROOM}).json()
    chosen = {i["slot_id"]: i["product"]["id"] for i in body["layout"]}
    assert "nightstand" in chosen and "desk" in chosen
    # Whatever desk was chosen, the recommendation must not introduce hard fails.
    assert body["evaluation"]["hard_fails"] == [], body["evaluation"]["hard_fails"]


def test_short_desk_keeps_chair_inside_room() -> None:
    # A 12 x 6 in desk (parser minimum is 6) is shorter than the 20 in chair; the chair is centered
    # on the desk, so it pokes 4 in through the bottom wall. Chair should be clamped inside the room.
    room = Room(width=144, depth=192, door=Door(wall="top", offset=56, width=32))
    ev = evaluate_layout(room, {"desk": (12.0, 6.0)})[2]
    assert not [f for f in ev.hard_fails if f.rule == "outside_room"]
