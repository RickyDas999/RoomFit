"""Evolving rooms: bed size follows the room, needs change the result, the planner adapts."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from test_api_fit import FakeCatalog, product

from app.beds import sizes_that_fit
from app.fit import evaluate_layout
from app.main import app, get_catalog
from app.room import Door, Rect, Room, Window, plan_room, public_slots

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    yield
    app.dependency_overrides.clear()


def room(w: float = 144, d: float = 192, door_offset: float = 56, **kw: object) -> Room:
    return Room(
        width=w,
        depth=d,
        door=Door(wall="top", offset=door_offset, width=32),
        window=Window(wall="bottom", offset=40, width=48),
        **kw,  # type: ignore[arg-type]
    )


def fits(r: Room) -> dict[str, bool]:
    return {s.role: s.fits for s in public_slots(r)}


# ---------- planner fallback ----------


def test_default_layout_is_unchanged_when_everything_fits() -> None:
    p = plan_room(room())
    assert not p.desk_on_top and not p.notes


@pytest.mark.parametrize("offset", [4, 108])  # door in either corner of the top wall
def test_door_in_a_corner_moves_the_desk_to_the_door_wall(offset: float) -> None:
    r = room(door_offset=offset)
    p = plan_room(r)
    assert p.desk_on_top and p.notes and "desk" in p.notes
    assert all(fits(r).values())
    # a real desk + chair placed there passes every rule
    ev = evaluate_layout(r, {"bed": (80, 40), "desk": (40, 22), "dresser": (36, 18)})[2]
    assert ev.hard_fails == [], ev.hard_fails
    assert ev.verdict == "fits"


def test_door_wall_chair_sits_below_the_desk_inside_the_room() -> None:
    r = room(w=144, d=160, door_offset=4)
    _, placed, ev = evaluate_layout(r, {"bed": (80, 40), "desk": (50, 38)})
    desk, chair = placed["desk"], placed["desk_chair"]
    assert chair.y == desk.y2 and desk.x <= chair.x and chair.x2 <= desk.x2
    assert ev.hard_fails == []


def test_closet_in_the_bed_corner_moves_the_bed_to_the_free_side() -> None:
    r = room(closet=Rect(x=100, y=150, w=44, d=42))
    p = plan_room(r)
    assert p.bed_side == "left" and p.notes and "bed" in p.notes


def test_a_unneeded_desk_does_not_trigger_the_fallback() -> None:
    p = plan_room(room(door_offset=4, needs=["dresser", "nightstand"]))
    assert not p.desk_on_top


def test_zones_for_a_door_wall_desk_sit_below_the_chair() -> None:
    from app.fit import zones_for

    r = room(door_offset=4)
    plan, placed, ev = evaluate_layout(r, {"bed": (80, 40), "desk": (40, 22)})
    z = next(z for z in zones_for(plan, placed, ev) if z.rule == "behind_desk_chair")
    c = placed["desk_chair"]
    assert z.rect.y == c.y2 and z.rect.x == c.x


# ---------- needs ----------


def test_missing_needs_follow_the_needs_field() -> None:
    r = room(needs=["nightstand"])  # no desk, no dresser wanted
    ev = evaluate_layout(r, {"bed": (80, 40)})[2]
    assert (
        ev.missing_needs == [] or ev.missing_needs == ["storage"] and r.closet is None
    )
    r2 = room(needs=["desk", "dresser", "nightstand"])
    assert "study" in evaluate_layout(r2, {"bed": (80, 40)})[2].missing_needs


def test_without_a_desk_need_the_verdict_can_reach_fits() -> None:
    r = room(needs=["dresser"], closet=Rect(x=0, y=0, w=48, d=24))
    ev = evaluate_layout(r, {"bed": (80, 40), "dresser": (36, 18)})[2]
    assert ev.missing_needs == [] and ev.verdict == "fits"


# ---------- bed sizes ----------


@pytest.mark.parametrize(
    ("across", "expected"),
    [
        (41, []),
        (42, ["twin_xl"]),
        (58, ["full", "twin_xl"]),
        (64, ["queen", "full", "twin_xl"]),
        (80, ["king", "queen", "full", "twin_xl"]),
    ],
)
def test_sizes_that_fit_largest_first(across: float, expected: list[str]) -> None:
    assert sizes_that_fit(120, across) == expected
    assert sizes_that_fit(60, 80) == []  # too short for any


def beds(w: float) -> dict[str, list]:  # type: ignore[type-arg]
    return {
        "king bed": [product("k", 700, (84, 80))],
        "queen bed": [product("q", 400, (64, 84))],
        "full bed": [product("f", 300, (58, 79))],
        "twin xl bed": [product("t", 200, (42, 83))],
        "nightstand": [product("n", 30, (16, 16))],
        "dresser": [product("d", 100, (30, 16))],
        "desk chair": [product("c", 40, None)],
        "desk": [product("e", 80, (40, 20))],
    }


@pytest.mark.parametrize(
    ("width", "size"), [(144, "twin_xl"), (152, "full"), (160, "queen"), (176, "king")]
)
def test_bigger_room_suggests_a_bigger_bed(width: float, size: str) -> None:
    use = FakeCatalog(beds(width))
    app.dependency_overrides[get_catalog] = lambda: use
    r = client.post(
        "/api/recommend", json={"room": room(w=width, d=216).model_dump()}
    ).json()
    assert r["bed_size"] == size
    assert any(i["slot_id"] == "bed" for i in r["layout"])
    assert size.replace("_", " ") in use.queries[-1] or any(
        size.replace("_", " ") in q for q in use.queries
    )


def test_chosen_bed_size_is_used_and_not_stepped_down() -> None:
    fake = FakeCatalog(beds(144))
    app.dependency_overrides[get_catalog] = lambda: fake
    r = client.post(
        "/api/recommend",
        json={"room": room(w=210, d=216).model_dump(), "bed_size": "full"},
    ).json()
    assert r["bed_size"] == "full" and "you chose" in r["bed_size_reason"]
    assert [q for q in fake.queries if "bed" in q] == ["full bed frame"]


def test_auto_steps_down_when_no_listing_of_the_big_size_fits() -> None:
    cat = beds(160)
    cat["queen bed"] = [product("q", 400, (90, 84))]  # a queen "frame" that is too wide
    fake = FakeCatalog(cat)
    app.dependency_overrides[get_catalog] = lambda: fake
    r = client.post(
        "/api/recommend", json={"room": room(w=160, d=216).model_dump()}
    ).json()
    assert r["bed_size"] == "full" and "too big" in r["bed_size_reason"]


# ---------- needs in /api/recommend ----------


def test_unneeded_pieces_are_not_searched_or_reported() -> None:
    fake = FakeCatalog(beds(144))
    app.dependency_overrides[get_catalog] = lambda: fake
    r = client.post(
        "/api/recommend", json={"room": room(needs=["nightstand"]).model_dump()}
    ).json()
    assert not any("desk" in q or "dresser" in q for q in fake.queries)
    assert {u["slot_id"] for u in r["unplaced"]} <= {"nightstand"}
    assert not any(
        i["slot_id"] in ("desk", "desk_chair", "dresser") for i in r["layout"]
    )


def test_needs_default_to_everything_and_reject_unknown_values() -> None:
    assert room().needs == ["nightstand", "dresser", "desk"]
    bad = room().model_dump() | {"needs": ["sofa"]}
    app.dependency_overrides[get_catalog] = lambda: FakeCatalog({})
    assert client.post("/api/recommend", json={"room": bad}).status_code == 422


# ---------- the listing must really be the searched size ----------


def test_a_too_small_listing_is_not_taken_for_a_big_size() -> None:
    cat = beds(176)
    cat["king bed"] = [
        product("k", 100, (57, 78))
    ]  # a "king" listing that is only 57 in wide
    fake = FakeCatalog(cat)
    app.dependency_overrides[get_catalog] = lambda: fake
    r = client.post(
        "/api/recommend", json={"room": room(w=176, d=216).model_dump()}
    ).json()
    assert r["bed_size"] == "queen" and "too big" in r["bed_size_reason"]


def test_a_chosen_size_with_no_matching_listing_places_no_bed_and_reports_no_size() -> (
    None
):
    cat = beds(176)
    cat["king bed"] = [product("k", 100, (57, 78))]
    app.dependency_overrides[get_catalog] = lambda: FakeCatalog(cat)
    r = client.post(
        "/api/recommend",
        json={"room": room(w=176, d=216).model_dump(), "bed_size": "king"},
    ).json()
    assert not any(i["slot_id"] == "bed" for i in r["layout"])
    assert r["bed_size"] is None and r["bed_size_reason"] is None
    assert [u["reason"] for u in r["unplaced"] if u["slot_id"] == "bed"]
