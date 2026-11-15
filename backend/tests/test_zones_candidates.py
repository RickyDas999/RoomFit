"""M4a: clearance zones, swap candidates, and the committed OpenAPI document."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_api_fit import BED, CATALOG, ROOM, FakeCatalog, layout_item, product

from app.dimensions import Dimensions
from app.fit import Footprints, evaluate_layout, orient, zones_for
from app.main import app, get_catalog
from app.room import SAMPLE_ROOM, Rect
from scripts.dump_openapi import PATH, render

client = TestClient(app)

GOOD: Footprints = {
    "bed": (80, 40),
    "desk": (48, 24),
    "dresser": (36, 20),
    "nightstand": (18, 16),
}


def zones(fp: Footprints) -> dict[str, tuple[float, float, float, float, bool, float]]:
    plan, placed, ev = evaluate_layout(SAMPLE_ROOM, fp)
    return {
        z.rule: (z.rect.x, z.rect.y, z.rect.w, z.rect.d, z.broken, z.short_in)
        for z in zones_for(plan, placed, ev)
    }


@pytest.fixture(autouse=True)
def _clean() -> None:
    app.dependency_overrides.clear()


# --- zones ---


def test_good_layout_has_five_unbroken_zones_with_the_right_geometry() -> None:
    z = zones(GOOD)
    assert set(z) == {
        "path_from_door",
        "bed_open_side",
        "in_front_of_dresser",
        "in_front_of_closet",
        "behind_desk_chair",
    }
    assert all(not v[4] and v[5] == 0 for v in z.values())
    assert z["path_from_door"][:4] == (54, 0, 36, 96)  # 36 in lane to the center line
    assert z["bed_open_side"][:4] == (
        80,
        112,
        24,
        80,
    )  # 24 in left of the bed (x 104-144)
    assert z["in_front_of_dresser"][:4] == (108, 20, 36, 24)  # below the dresser
    assert z["in_front_of_closet"][:4] == (0, 24, 48, 24)  # below the closet
    assert z["behind_desk_chair"][:4] == (44, 158, 18, 20)  # 18 in behind the chair


def test_with_no_furniture_only_the_path_and_closet_zones_exist() -> None:
    assert set(zones({})) == {"path_from_door", "in_front_of_closet"}


def test_broken_zones_carry_the_inches_short() -> None:
    z = zones({"bed": (80, 40), "desk": orient(Dimensions(w=72, d=72))})
    assert z["behind_desk_chair"][4:] == (True, 6)
    assert z["bed_open_side"][4:] == (True, 12)
    assert z["path_from_door"][4] is False


def test_path_zone_breaks_when_furniture_blocks_the_lane() -> None:
    z = zones({**GOOD, "dresser": (60, 30)})
    assert z["path_from_door"][4:] == (True, 6)


def test_zone_broken_flags_match_the_hard_fails_exactly() -> None:
    layouts: list[Footprints] = [
        GOOD,
        {**GOOD, "desk": (48, 54)},
        {**GOOD, "dresser": (60, 30)},
        {"bed": (80, 70)},
    ]
    for fp in layouts:
        plan, placed, ev = evaluate_layout(SAMPLE_ROOM, fp)
        broken = {z.rule for z in zones_for(plan, placed, ev) if z.broken}
        wanted = {f.rule for f in ev.hard_fails} & {
            "path_from_door",
            "bed_open_side",
            "in_front_of_dresser",
            "in_front_of_closet",
            "behind_desk_chair",
        }
        assert broken == wanted, fp


@pytest.mark.parametrize("wall", ["top", "bottom", "left", "right"])
def test_api_zones_are_in_the_rooms_own_coordinates(wall: str) -> None:
    sideways = wall in ("left", "right")
    room: dict[str, Any] = {
        "width": 192 if sideways else 144,
        "depth": 144 if sideways else 192,
        "door": {"wall": wall, "offset": 56, "width": 32},
    }
    layout = [
        layout_item("bed", product("b", 1, BED)),
        layout_item("desk", product("d", 1, (48, 24))),
    ]
    body = client.post("/api/evaluate", json={"room": room, "layout": layout}).json()
    assert {z["rule"] for z in body["zones"]} >= {
        "path_from_door",
        "bed_open_side",
        "behind_desk_chair",
    }
    for z in body["zones"]:
        r = z["rect"]
        assert r["w"] > 0 and r["d"] > 0
        assert -1e-6 <= r["x"] and r["x"] + r["w"] <= room["width"] + 1e-6, z
        assert -1e-6 <= r["y"] and r["y"] + r["d"] <= room["depth"] + 1e-6, z
    bed = Rect.model_validate(body["placed"]["bed"])
    zone = Rect.model_validate(
        next(z["rect"] for z in body["zones"] if z["rule"] == "bed_open_side")
    )
    touches = (
        abs(zone.x2 - bed.x) < 1e-6
        or abs(zone.x - bed.x2) < 1e-6
        or abs(zone.y2 - bed.y) < 1e-6
        or abs(zone.y - bed.y2) < 1e-6
    )
    assert touches  # the shaded strip sits right against the bed


def test_evaluate_with_an_empty_layout_still_returns_slots_and_zones() -> None:
    body = client.post("/api/evaluate", json={"room": ROOM, "layout": []}).json()
    assert body["slots"][0]["id"] == "bed"
    assert {z["rule"] for z in body["zones"]} == {
        "path_from_door",
        "in_front_of_closet",
    }


# --- candidates ---


def recommend() -> dict[str, Any]:
    app.dependency_overrides[get_catalog] = lambda: FakeCatalog(CATALOG)
    body: dict[str, Any] = client.post("/api/recommend", json={"room": ROOM}).json()
    return body


def test_candidates_list_every_searched_product_cheapest_first() -> None:
    body = recommend()
    cands = body["candidates"]
    assert set(cands) == {"bed", "desk", "desk_chair", "dresser", "nightstand"}
    for role, items in cands.items():
        prices = [c["product"]["price"]["amount"] for c in items]
        assert prices == sorted(prices), role
    assert [
        len(cands[r]) for r in ("bed", "desk", "desk_chair", "dresser", "nightstand")
    ] == [4, 4, 2, 2, 2]


def test_candidates_flag_which_products_fit_the_slot() -> None:
    cands = recommend()["candidates"]
    fits = {
        c["product"]["id"].split("/")[-1]: c["fits_slot"]
        for c in cands["bed"] + cands["desk"]
    }
    assert fits == {
        "bed-nodims": False,  # no dimensions
        "bed-toowide": False,  # 70 in across, slot allows 54
        "bed-cheap": True,
        "bed-pricey": True,
        "desk-huge": False,  # 110 in long, slot allows 96
        "desk-deep": True,  # fits the space; the rules decide on swap
        "desk-ok": True,
        "desk-ok2": True,
    }


def test_chair_candidates_always_fit_because_the_size_is_assumed() -> None:
    cands = recommend()["candidates"]
    assert all(c["fits_slot"] for c in cands["desk_chair"])


def test_every_chosen_product_is_among_the_candidates() -> None:
    body = recommend()
    for item in body["layout"]:
        ids = [c["product"]["id"] for c in body["candidates"][item["slot_id"]]]
        assert item["product"]["id"] in ids


def test_candidates_include_the_products_the_user_cannot_get_a_size_for() -> None:
    cands = recommend()["candidates"]
    missing = [c for c in cands["bed"] if c["product"]["dimensions"] is None]
    assert [c["product"]["dimension_status"] for c in missing] == ["missing"]


def test_slot_with_no_space_has_an_empty_candidate_list() -> None:
    room = {
        **ROOM,
        "width": 40,
        "depth": 50,
        "door": {"wall": "top", "offset": 4, "width": 32},
        "closet": None,
        "window": None,
    }
    app.dependency_overrides[get_catalog] = lambda: FakeCatalog(CATALOG)
    cands = client.post("/api/recommend", json={"room": room}).json()["candidates"]
    assert cands["desk"] == [] and cands["desk_chair"] == []


def test_recommend_response_carries_zones_too() -> None:
    body = recommend()
    assert {z["rule"] for z in body["zones"]} >= {"path_from_door"}


# --- the committed OpenAPI document ---


def test_committed_openapi_json_is_up_to_date() -> None:
    assert Path(PATH).read_text() == render(), (
        "backend/openapi.json is out of date: run `python -m scripts.dump_openapi` "
        "from backend/, then `npm run gen:api` in frontend/"
    )
