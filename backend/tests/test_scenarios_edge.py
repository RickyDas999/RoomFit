"""Edge and adversarial tests for evolving rooms: needs, bed sizes, planner fallbacks."""

import random
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from test_api_fit import FakeCatalog, product

from app.fit import evaluate_layout, evaluate_placed, place_all, zones_for
from app.main import app, get_catalog
from app.room import Door, Rect, Room, Wall, Window, _plan, plan_room, public_slots

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    yield
    app.dependency_overrides.clear()


def use(fake: FakeCatalog) -> None:
    app.dependency_overrides[get_catalog] = lambda: fake


def make_room(w: float, d: float, wall: Wall, offset: float, **kw: object) -> Room:
    return Room(
        width=w, depth=d, door=Door(wall=wall, offset=offset, width=32), **kw  # type: ignore[arg-type]
    )


def inside(r: Rect, w: float, d: float) -> bool:
    return r.x >= -1e-6 and r.y >= -1e-6 and r.x2 <= w + 1e-6 and r.y2 <= d + 1e-6


def max_fp(room: Room, top: bool, side: str | None) -> tuple[object, dict]:  # type: ignore[type-arg]
    plan = _plan(room, side, top)  # type: ignore[arg-type]
    fp = {
        r: (sp.max_along, sp.max_across)
        for r, sp in plan.slots.items()
        if sp.fits and r != "desk_chair" and (r == "bed" or r in room.needs)
    }
    return plan, fp


# ---------- door-wall desk on every wall ----------


@pytest.mark.parametrize("wall", ["top", "bottom", "left", "right"])
@pytest.mark.parametrize("at_end", [False, True])
def test_door_wall_desk_with_the_door_on_every_wall(wall: Wall, at_end: bool) -> None:
    long_wall = wall in ("top", "bottom")
    w, d = (144.0, 160.0) if long_wall else (160.0, 144.0)
    length = w if long_wall else d
    r = make_room(w, d, wall, length - 32 - 4 if at_end else 4)
    plan, placed, ev = evaluate_layout(
        r, {"bed": (80, 40), "desk": (40, 22), "dresser": (36, 18)}
    )
    assert plan.desk_on_top
    assert inside(Rect(x=0, y=0, w=plan.W, d=plan.D), plan.W, plan.D)
    back = {n: plan.frame.rect_back(rect) for n, rect in placed.items()}  # room coordinates
    for name, rect in back.items():
        assert inside(rect, w, d), (name, rect)
    names = list(back)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            assert not back[a].intersects(back[b]), (a, b)
    assert ev.hard_fails == [], ev.hard_fails
    for z in zones_for(plan, placed, ev):
        assert inside(plan.frame.rect_back(z.rect), w, d), (z.rule, z.rect)


def test_door_wall_chair_is_flush_below_the_desk_in_every_frame() -> None:
    for wall in ("top", "bottom", "left", "right"):
        r = make_room(144, 144, wall, 4)
        plan, placed, _ = evaluate_layout(r, {"bed": (80, 40), "desk": (40, 22)})
        assert plan.desk_on_top
        desk, chair = placed["desk"], placed["desk_chair"]  # canonical: door on top
        assert chair.y == pytest.approx(desk.y2), wall
        assert desk.x <= chair.x + 1e-6 and chair.x2 <= desk.x2 + 1e-6, wall


# ---------- property test over random rooms ----------


def random_room(rng: random.Random) -> Room:
    wall: Wall = rng.choice(["top", "bottom", "left", "right"])
    w, d = float(rng.randint(90, 260)), float(rng.randint(90, 260))
    length = w if wall in ("top", "bottom") else d
    needs = [n for n in ("nightstand", "dresser", "desk") if rng.random() < 0.7]
    kw: dict[str, object] = {"needs": needs}
    if rng.random() < 0.5:
        kw["closet"] = Rect(x=0, y=0, w=48, d=24)
    return make_room(w, d, wall, rng.uniform(0, length - 32), **kw)


@pytest.mark.parametrize("top", [False, True])
@pytest.mark.parametrize("flip", [False, True])
def test_every_variant_accepts_its_own_max_footprints(top: bool, flip: bool) -> None:
    rng = random.Random(1234)
    checked = 0
    for _ in range(300):
        r = random_room(rng)
        base = _plan(r, None, False)
        side = ("left" if base.bed_side == "right" else "right") if flip else base.bed_side
        plan, fp = max_fp(r, top, side)
        # only judge variants the planner could actually pick for this room
        if not plan.slots["bed"].fits:  # type: ignore[attr-defined]
            continue
        placed = place_all(plan, fp)  # type: ignore[arg-type]
        ev = evaluate_placed(plan, placed)  # type: ignore[arg-type]
        bad = [f for f in ev.hard_fails if f.rule in ("outside_room", "overlap", "path_from_door") and "closet" not in f.pieces
               and set(f.pieces) != {"nightstand", "desk_chair"}]  # see the xfail below
        assert not bad, (r.model_dump(), top, flip, bad)
        checked += 1
    assert checked > 50


@pytest.mark.xfail(
    strict=True,
    reason="APP BUG: the nightstand slot spans the whole lane width, but the desk chair may poke "
    "into the lane; a max-footprint nightstand overlaps the chair (evaluate reports overlap)",
)
def test_max_nightstand_does_not_overlap_the_desk_chair() -> None:
    r = make_room(180, 150, "top", 72, needs=["nightstand", "desk"])
    plan, fp = max_fp(r, False, None)
    ev = evaluate_placed(plan, place_all(plan, fp))  # type: ignore[arg-type]
    assert not [f for f in ev.hard_fails if f.rule == "overlap"]


def test_public_slots_are_well_formed_for_random_rooms() -> None:
    rng = random.Random(99)
    for _ in range(200):
        r = random_room(rng)
        slots = public_slots(r)
        assert {s.role for s in slots} == {"bed", "desk", "desk_chair", "dresser", "nightstand"}
        for s in slots:
            assert s.max_footprint[0] >= 0 and s.max_footprint[1] >= 0
            assert s.fits or s.note and s.note.startswith("no ")


# ---------- needs ----------


@pytest.mark.parametrize(
    "needs",
    [[], ["nightstand"], ["dresser"], ["desk"], ["desk", "desk"], ["dresser", "nightstand", "desk"]],
)
def test_needs_permutations_plan_and_evaluate(needs: list[str]) -> None:
    r = make_room(144, 192, "top", 56, needs=needs)
    plan = plan_room(r)
    ev = evaluate_layout(r, {"bed": (80, 40)})[2]
    assert ev.hard_fails == []
    assert ("study" in ev.missing_needs) == ("desk" in needs)
    assert ("storage" in ev.missing_needs) == ("dresser" in needs)
    assert plan.needs == frozenset(needs)


def test_no_needs_means_bed_only_recommend() -> None:
    fake = FakeCatalog({"bed": [product("b", 200, (42, 83))]})
    use(fake)
    res = client.post(
        "/api/recommend", json={"room": make_room(144, 192, "top", 56, needs=[]).model_dump()}
    ).json()
    assert len(fake.queries) == 1 and "bed" in fake.queries[0]
    assert [i["slot_id"] for i in res["layout"]] == ["bed"]
    assert res["unplaced"] == []
    assert res["evaluation"]["missing_needs"] == []


def test_duplicate_needs_do_not_break_recommend() -> None:
    fake = FakeCatalog({"bed": [product("b", 200, (42, 83))], "desk": [product("e", 80, (40, 20))]})
    use(fake)
    room = make_room(144, 192, "top", 56).model_dump() | {"needs": ["desk", "desk"]}
    res = client.post("/api/recommend", json={"room": room})
    assert res.status_code == 200
    assert sum("desk chair" in q for q in fake.queries) <= 1
    ids = [i["slot_id"] for i in res.json()["layout"]]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("needs", [["bed"], ["Desk"], [None], "desk", ["desk_chair"]])
def test_unknown_or_bad_needs_are_rejected(needs: object) -> None:
    use(FakeCatalog({}))
    room = make_room(144, 192, "top", 56).model_dump() | {"needs": needs}
    assert client.post("/api/recommend", json={"room": room}).status_code == 422
    assert client.post("/api/evaluate", json={"room": room, "layout": []}).status_code == 422


@pytest.mark.parametrize("needs", [[], ["nightstand"], ["dresser"], ["desk"], ["nightstand", "desk"]])
def test_recommend_never_searches_unneeded_roles(needs: list[str]) -> None:
    fake = FakeCatalog({})
    use(fake)
    client.post(
        "/api/recommend", json={"room": make_room(176, 216, "top", 72, needs=needs).model_dump()}
    )
    qs = " | ".join(fake.queries)
    assert ("nightstand" in qs) == ("nightstand" in needs)
    assert ("dresser" in qs) == ("dresser" in needs)
    assert ("desk" in qs) == ("desk" in needs)


# ---------- bed sizes ----------


def full_catalog() -> dict[str, list]:  # type: ignore[type-arg]
    return {
        "king bed": [product("k", 700, (84, 80))],
        "queen bed": [product("q", 400, (64, 84))],
        "full bed": [product("f", 300, (58, 79))],
        "twin xl bed": [product("t", 200, (42, 83))],
    }


def test_bed_size_override_on_a_room_too_small_for_it() -> None:
    fake = FakeCatalog(full_catalog())
    use(fake)
    r = client.post(
        "/api/recommend",
        json={"room": make_room(144, 192, "top", 56).model_dump(), "bed_size": "king"},
    ).json()
    assert [q for q in fake.queries if "bed" in q] == ["king bed frame"]
    assert not any(i["slot_id"] == "bed" for i in r["layout"])  # the king cannot fit
    assert any(u["slot_id"] == "bed" for u in r["unplaced"])
    assert r["bed_size"] is None and r["bed_size_reason"] is None  # nothing placed, no size claimed


def test_bed_size_rejects_unknown_values() -> None:
    use(FakeCatalog({}))
    res = client.post(
        "/api/recommend",
        json={"room": make_room(144, 192, "top", 56).model_dump(), "bed_size": "emperor"},
    )
    assert res.status_code == 422


def test_auto_steps_down_when_listings_lack_dimensions() -> None:
    cat = full_catalog()
    cat["queen bed"] = [product("q", 400, None)]
    cat["king bed"] = [product("k", 700, None)]
    use(FakeCatalog(cat))
    r = client.post(
        "/api/recommend", json={"room": make_room(176, 216, "top", 72).model_dump()}
    ).json()
    assert r["bed_size"] in ("full", "twin_xl")
    assert any(i["slot_id"] == "bed" for i in r["layout"])
    assert "too big" in r["bed_size_reason"]


def test_auto_steps_down_when_the_big_size_returns_nothing() -> None:
    cat = full_catalog()
    cat["king bed"] = []
    cat["queen bed"] = []
    fake = FakeCatalog(cat)
    use(fake)
    r = client.post(
        "/api/recommend", json={"room": make_room(176, 216, "top", 72).model_dump()}
    ).json()
    assert r["bed_size"] in ("full", "twin_xl")
    bed_q = [q for q in fake.queries if "bed" in q]
    assert bed_q[0].startswith(("king", "queen")) and len(bed_q) >= 2


def test_every_size_empty_reports_the_bed_unplaced_without_a_reason_claim() -> None:
    use(FakeCatalog({}))
    r = client.post(
        "/api/recommend", json={"room": make_room(176, 216, "top", 72).model_dump()}
    ).json()
    assert r["layout"] == [] or all(i["slot_id"] != "bed" for i in r["layout"])
    assert any(u["slot_id"] == "bed" for u in r["unplaced"])
    assert r["bed_size_reason"] is None


def test_coverage_guard_skips_a_bed_that_overfills_a_tiny_room() -> None:
    # a small room: a huge bed listing pushes coverage past the warning line; a slimmer one is chosen
    room = make_room(120, 168, "top", 44, needs=[])
    cat = {"twin xl bed": [product("huge", 100, (42, 83)), product("ok", 300, (42, 80))]}
    use(FakeCatalog(cat))
    r = client.post("/api/recommend", json={"room": room.model_dump()}).json()
    cov = r["evaluation"]["coverage_pct"]
    chosen = [i for i in r["layout"] if i["slot_id"] == "bed"]
    # whichever is picked, a chosen bed never leaves the room beyond the coverage warning
    assert not chosen or cov <= 40.0 or r["evaluation"]["coverage_status"] != "ok"


def test_catalog_error_during_the_bed_search_is_a_502() -> None:
    use(FakeCatalog({}, fail=True))
    r = client.post(
        "/api/recommend",
        json={"room": make_room(144, 192, "top", 56, needs=[]).model_dump()},
    )
    assert r.status_code == 502, r.text
    assert "catalog error" in r.json()["detail"]


def test_catalog_error_on_a_later_bed_size_is_a_502() -> None:
    from app.catalog import CatalogError

    class Flaky(FakeCatalog):
        async def search(self, query: str, limit: int = 25) -> list:  # type: ignore[type-arg]
            if "queen" in query:
                raise CatalogError("boom")
            return await super().search(query, limit)

    use(Flaky({"king bed": []}))
    r = client.post(
        "/api/recommend", json={"room": make_room(176, 216, "top", 72, needs=[]).model_dump()}
    )
    assert r.status_code == 502, r.text


def test_window_and_closet_rooms_still_report_bed_size_fields() -> None:
    use(FakeCatalog(full_catalog()))
    room = make_room(
        144, 192, "top", 56, window=Window(wall="bottom", offset=48, width=48),
        closet=Rect(x=0, y=0, w=48, d=24),
    )
    r = client.post("/api/recommend", json={"room": room.model_dump()}).json()
    assert r["bed_size"] == "twin_xl" and r["bed_size_reason"]
