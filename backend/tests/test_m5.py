"""M5: confidence classes, tech_specs, bed size sanity check, rotation, data-gap counts."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_api_fit import FakeCatalog, product
from test_catalog import make_product

from app.beds import title_size_mismatch
from app.catalog import Product, parse_product
from app.dimensions import parse_tech_specs
from app.main import app, get_catalog
from app.room import SAMPLE_ROOM

client = TestClient(app)
ROOM = SAMPLE_ROOM.model_dump()


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    yield
    app.dependency_overrides.clear()


def raw(desc: str, specs: Any = None, title: str = "Test Desk") -> dict[str, Any]:
    p = make_product(title=title, description={"html": f"<p>{desc}</p>"})
    if specs is not None:
        p["metadata"] = {"tech_specs": specs}
    return p


# ---------- tech_specs parser ----------


def test_tech_specs_overall_dimensions_are_read() -> None:
    r = parse_tech_specs(
        ["Material: MDF", "Overall Dimensions: 48 x 24 x 43.5 in (L x W x H)"]
    )
    assert r.status == "parsed" and r.dimensions
    assert (r.dimensions.w, r.dimensions.d, r.dimensions.h) == (48, 24, 43.5)


def test_tech_specs_ignore_parts_of_the_product() -> None:
    specs = [
        "Drawer Interior Dimensions: 15 x 11 x 4 in (W x D x H)",
        "Legroom Size: 26 x 29.5 in",
        "Package Dimensions: 50 x 26 x 6 in",
        "Mattress Size: 60 x 80 in",
        "Desktop Sizes: 40 x 24 in, 48 x 24 in",
    ]
    assert parse_tech_specs(specs).status == "missing"


def test_tech_specs_same_size_in_inches_and_cm_is_one_size() -> None:
    r = parse_tech_specs(
        ["Overall Dimensions: 48 x 24 x 29.5 in (121.9 x 61 x 74.9 cm)"]
    )
    assert r.status == "parsed"


def test_tech_specs_two_different_overall_sizes_are_ambiguous() -> None:
    r = parse_tech_specs(
        ["Product Dimensions: 48 x 24 x 30 in", "Overall Size: 60 x 30 x 30 in"]
    )
    assert (
        r.status == "ambiguous"
        and r.reason == "multiple_sizes"
        and len(r.candidates) == 2
    )


@pytest.mark.parametrize(
    "specs", [[], ["no colon here"], ["Dimensions:"], ["Size: large"]]
)
def test_tech_specs_with_nothing_usable_are_missing(specs: list[str]) -> None:
    assert parse_tech_specs(specs).status == "missing"


# ---------- confidence classes ----------


def test_stated_when_the_description_has_a_clear_size() -> None:
    p = parse_product(raw('Desk 40"W x 20"D x 30"H'))
    assert p and p.dimension_confidence == "stated" and p.dimension_status == "parsed"


def test_inferred_when_only_the_tech_specs_have_it() -> None:
    p = parse_product(raw("A sturdy desk.", ["Overall Dimensions: 48 x 24 x 30 in"]))
    assert p and p.dimension_confidence == "inferred" and p.dimension_status == "parsed"
    assert p.dimensions and p.dimensions.w == 48
    assert p.dimension_source == "48 x 24 x 30 in"


def test_the_description_beats_the_tech_specs() -> None:
    p = parse_product(raw('Desk 40"W x 20"D', ["Overall Dimensions: 48 x 24 x 30 in"]))
    assert (
        p
        and p.dimension_confidence == "stated"
        and p.dimensions
        and p.dimensions.w == 40
    )


def test_ambiguous_description_is_rescued_by_clear_tech_specs() -> None:
    p = parse_product(
        raw(
            "Package dimensions: 60 x 30 x 8 in.",
            ["Product Dimensions: 48 x 24 x 30 in"],
        )
    )
    assert (
        p
        and p.dimension_confidence == "inferred"
        and p.dimensions
        and p.dimensions.w == 48
    )


def test_ambiguous_when_nothing_clear_is_found() -> None:
    p = parse_product(raw("Package dimensions: 60 x 30 x 8 in."))
    assert p and p.dimension_confidence == "ambiguous" and p.dimensions is None
    assert p.dimension_reason == "shipping_size"


def test_ambiguous_tech_specs_alone_are_ambiguous_not_missing() -> None:
    p = parse_product(
        raw(
            "A desk.",
            ["Product Dimensions: 48 x 24 x 30 in", "Overall Size: 60 x 30 x 30 in"],
        )
    )
    assert p and p.dimension_confidence == "ambiguous" and p.dimensions is None


def test_missing_when_there_is_nothing() -> None:
    p = parse_product(raw("A desk.", ["Material: wood"]))
    assert p and p.dimension_confidence == "missing" and p.dimensions is None


@pytest.mark.parametrize(
    "specs", ["Overall Dimensions: 48 x 24 in", {"a": 1}, 7, [1, None, {"x": 2}]]
)
def test_malformed_tech_specs_never_crash(specs: Any) -> None:
    p = parse_product(raw("A desk.", specs))
    assert p and p.dimension_confidence == "missing"


# ---------- bed size sanity check ----------


def test_a_queen_listed_55_wide_is_not_placed() -> None:
    p = parse_product(raw("Frame 81.4 x 55.1 x 7.9 in", title="Queen Size Bed Frame"))
    assert (
        p
        and p.dimension_confidence == "ambiguous"
        and p.dimension_reason == "size_mismatch"
    )
    assert p.dimensions is None and p.dimension_status == "ambiguous"


def test_a_real_queen_passes_and_a_mismatched_inferred_size_is_caught_too() -> None:
    ok = parse_product(raw("Frame 83.7 x 64.8 x 37 in", title="Queen Bed Frame"))
    assert ok and ok.dimension_confidence == "stated" and ok.dimensions
    bad = parse_product(
        raw(
            "A bed.",
            ["Overall Dimensions: 78 x 57.1 x 42.9 in"],
            title="King Size Bed Frame",
        )
    )
    assert bad and bad.dimension_reason == "size_mismatch"


@pytest.mark.parametrize(
    ("title", "along", "across", "bad"),
    [
        ("King Size Bed Frame", 78, 57.1, True),
        ("King Size Bed Frame", 84, 78, False),
        ("Twin XL Bed Frame", 80, 38, False),
        ("Twin XL Bed Frame", 70, 38, True),
        ("Full Size Bed Frame", 75, 54, False),
        ("Full Size Bed Frame", 75, 40, True),
        ("California King Bed Frame", 84, 72, False),
        ("Twin/Full/Queen Bed Frame", 50, 30, False),  # several sizes: not checked
        ("Queen Size Desk", 50, 30, False),  # not a bed
        ("Bed Frame", 50, 30, False),  # no size named
        (
            "Full Length Mirror Bed Frame Organizer",
            50,
            30,
            False,
        ),  # "full" is not a size here
        ("Queen Bed Frame", 55.1, 81.4, True),  # either order
    ],
)
def test_title_size_mismatch(
    title: str, along: float, across: float, bad: bool
) -> None:
    assert title_size_mismatch(title, along, across) is bad


# ---------- rotation ----------


def use(fake: FakeCatalog) -> None:
    app.dependency_overrides[get_catalog] = lambda: fake


def test_evaluate_tries_both_ways_and_reports_the_turned_piece() -> None:
    dresser = product(
        "d", 50, (60, 30)
    )  # too long for the dresser slot's width unless turned
    item = {"slot_id": "dresser", "product": dresser.model_dump()}

    def run(**extra: object) -> dict[str, Any]:
        res = client.post(
            "/api/evaluate", json={"room": ROOM, "layout": [{**item, **extra}]}
        )
        body: dict[str, Any] = res.json()
        return body

    auto, plain, turned = run(), run(rotated=False), run(rotated=True)
    assert plain["rotated"] == [] and turned["rotated"] == ["dresser"]
    assert (
        plain["evaluation"]["hard_fails"] != []
    )  # long side along the wall: sticks out of the slot
    assert turned["evaluation"]["hard_fails"] == []  # turned: a pass
    assert auto["rotated"] == ["dresser"] and auto["evaluation"]["hard_fails"] == []


def test_a_rotation_turns_a_fail_into_a_pass_in_recommend() -> None:
    from app.room import plan_room

    sp = plan_room(SAMPLE_ROOM).slots["dresser"]
    assert (
        60 > sp.max_along and 30 <= sp.max_along and 60 <= sp.max_across
    )  # only fits turned
    use(FakeCatalog({"dresser": [product("d", 50, (60, 30))]}))
    r = client.post("/api/recommend", json={"room": ROOM}).json()
    got = next(i for i in r["layout"] if i["slot_id"] == "dresser")
    assert got["rotated"] is True and r["rotated"] == ["dresser"]
    assert r["evaluation"]["hard_fails"] == []
    cand = r["candidates"]["dresser"][0]
    assert cand["fits_slot"] is True  # offered as fitting because it can be turned


def test_a_piece_that_fits_either_way_keeps_its_long_side_along_the_wall() -> None:
    use(FakeCatalog({"dresser": [product("d", 50, (40, 20))]}))
    r = client.post("/api/recommend", json={"room": ROOM}).json()
    got = next(i for i in r["layout"] if i["slot_id"] == "dresser")
    assert got["rotated"] is False and r["rotated"] == []


def test_a_piece_too_big_even_turned_is_still_refused() -> None:
    use(FakeCatalog({"dresser": [product("d", 50, (90, 80))]}))
    r = client.post("/api/recommend", json={"room": ROOM}).json()
    assert not any(i["slot_id"] == "dresser" for i in r["layout"])


# ---------- data-gap counts ----------


def test_search_stats_count_each_confidence_class() -> None:
    def prod(pid: str, conf: str, dims: tuple[float, float] | None) -> Product:
        return product(pid, 10, dims).model_copy(update={"dimension_confidence": conf})

    use(
        FakeCatalog(
            {
                "desk chair": [product("c", 40, None)],
                "desk": [
                    prod("a", "stated", (48, 24)),
                    prod("b", "inferred", (50, 24)),
                    prod("c1", "inferred", (52, 24)),
                    prod("d", "ambiguous", None),
                    prod("e", "missing", None),
                    prod("f", "missing", None),
                ],
            }
        )
    )
    s = client.post("/api/recommend", json={"room": ROOM}).json()["searched"]["desk"]
    assert (s["found"], s["with_dimensions"]) == (6, 3)
    assert (s["stated"], s["inferred"], s["ambiguous"], s["missing"]) == (1, 2, 1, 2)
