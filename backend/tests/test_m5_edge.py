"""Adversarial M5 tests: tech_specs parsing, size check, rotation, counts."""

import random
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


def use(fake: FakeCatalog) -> None:
    app.dependency_overrides[get_catalog] = lambda: fake


def raw(desc: str, metadata: Any = None, title: str = "Test Desk") -> dict[str, Any]:
    p = make_product(title=title, description={"html": f"<p>{desc}</p>"})
    if metadata is not None:
        p["metadata"] = metadata
    return p


# ---------- tech_specs ----------


@pytest.mark.parametrize(
    ("line", "wd"),
    [
        ("Overall Dimensions: 48 x 24 x 43.5 in (L x W x H)", (48, 24)),
        ("Dimensions: 120 x 60 x 75 cm", (47.24, 23.62)),
        ("OVERALL DIMENSIONS: 48 x 24 in", (48, 24)),
        ("overall dimensions: 48 × 24 in", (48, 24)),
        ("Item Size: 48 x 24 in", (48, 24)),
        ("Dimensions: 4 ft x 2 ft", (48, 24)),
        ("Dimensions: 48 1/2 x 24 in", (48.5, 24)),
    ],
)
def test_tech_specs_realistic_lines(line: str, wd: tuple[float, float]) -> None:
    r = parse_tech_specs(["Material: Oak", line])
    assert r.status == "parsed" and r.dimensions
    assert (r.dimensions.w, r.dimensions.d) == pytest.approx(wd, abs=0.01)


def test_tech_specs_duplicate_lines_are_one_size() -> None:
    line = "Overall Dimensions: 48 x 24 x 30 in"
    assert parse_tech_specs([line, line, line.lower()]).status == "parsed"


def test_tech_specs_two_different_sizes_are_ambiguous() -> None:
    r = parse_tech_specs(["Dimensions: 48 x 24 in", "Overall Dimensions: 60 x 30 in"])
    assert r.status == "ambiguous" and r.reason == "multiple_sizes"


@pytest.mark.parametrize(
    "line",
    [
        "Seat Height: 18 in",
        "Bed Size: Queen",
        "Mattress Size: Full",
        "Size: Large",
        "Dimensions: 48 x 24",  # no unit
        "Dimensions: 4800 x 2400 in",
        "Dimensions: 1 x 1 in",
        "Dimensions 48 x 24 in",  # no colon
        "",
        ":",
        "Dimensions:",
    ],
)
def test_tech_specs_lines_that_are_not_a_size(line: str) -> None:
    assert parse_tech_specs([line]).status in ("missing", "ambiguous")
    assert parse_tech_specs([line]).dimensions is None


def test_tech_specs_very_long_list_and_junk_do_not_crash() -> None:
    specs = [f"Feature {i}: value {i} x {i} in" for i in range(5000)]
    specs.append("Overall Dimensions: 48 x 24 in")
    r = parse_tech_specs(specs)
    assert r.status == "parsed"


def test_tech_specs_unicode_x() -> None:
    assert parse_tech_specs(["Dimensions: 48 ✕ 24 in"]).status == "parsed"


@pytest.mark.parametrize(
    "meta",
    [
        None,
        {},
        {"tech_specs": None},
        {"tech_specs": "Overall Dimensions: 48 x 24 in"},
        {"tech_specs": {"a": "b"}},
        {"tech_specs": [{"label": "Dimensions", "value": "48 x 24 in"}]},
        {"tech_specs": [None, 5, ["Dimensions: 48 x 24 in"]]},
        {"tech_specs": []},
        [],
        "oops",
    ],
)
def test_parse_product_with_weird_metadata_shapes(meta: Any) -> None:
    p = parse_product(raw("A desk.", meta))
    if p is None:  # a non-dict metadata is allowed to reject the listing, not crash
        assert not isinstance(meta, dict)
        return
    assert p.dimension_confidence == "missing" and p.dimensions is None


def test_parse_product_mixed_list_keeps_the_string_entries() -> None:
    p = parse_product(
        raw("A desk.", {"tech_specs": [None, 7, "Overall Dimensions: 48 x 24 in"]})
    )
    assert p and p.dimension_confidence == "inferred" and p.dimensions


def test_description_wins_over_tech_specs() -> None:
    p = parse_product(
        raw("Desk 40 x 20 in", {"tech_specs": ["Overall Dimensions: 60 x 30 in"]})
    )
    assert p and p.dimension_confidence == "stated" and p.dimensions
    assert (p.dimensions.w, p.dimensions.d) == (40, 20)


def test_a_description_with_several_sizes_is_not_overruled_by_the_specs() -> None:
    p = parse_product(
        raw(
            "Sizes 40 x 20 in or 60 x 30 in",
            {"tech_specs": ["Overall Dimensions: 48 x 24 in"]},
        )
    )
    # the specs' one size could be a different variant of the listing
    assert p and p.dimension_confidence == "ambiguous" and p.dimensions is None


def test_confidence_always_agrees_with_status() -> None:
    cases = [
        raw("Desk 40 x 20 in"),
        raw("nothing"),
        raw("Sizes 40 x 20 in or 60 x 30 in"),
        raw("x", {"tech_specs": ["Dimensions: 48 x 24 in"]}),
        raw("x", {"tech_specs": ["Dimensions: 48 x 24 in", "Size: 60 x 30 in"]}),
        raw("Frame 81 x 55 in", title="Queen Bed Frame"),
    ]
    for c in cases:
        p = parse_product(c)
        assert p
        if p.dimension_confidence in ("stated", "inferred"):
            assert p.dimension_status == "parsed" and p.dimensions
        else:
            assert p.dimension_status == p.dimension_confidence
            assert p.dimensions is None


# ---------- size check ----------


@pytest.mark.parametrize(
    ("title", "along", "across", "bad"),
    [
        ("Queen Bed Frame", 78, 58, False),  # exactly 2 in under both: allowed
        ("Queen Bed Frame", 77.9, 60, True),
        ("Queen Bed Frame", 80, 57.9, True),
        ("Queen Bed Frame", 82, 62, False),
        ("Queen Bed Frame", 58, 78, False),  # swapped
        ("Queen Bed Frame", 57.9, 80, True),
        ("Twin XL Bed Frame", 80, 38, False),
        ("Twin Bed Frame", 75, 38, False),
        ("Twin Bed Frame", 70, 38, True),
        ("Twin-XL Platform Bed", 72, 38, True),
        ("Twin XL Platform Bed", 78, 36, False),
        ("Queen/King Bed Frame", 20, 20, False),
        ("Queen or King Bed Frame", 20, 20, False),
        ("King Bed Frame", 20, 20, True),
        ("Cal King Bed Frame", 84, 72, False),
        ("Cal King Bed Frame", 80, 60, True),
        ("QUEEN BED FRAME", 20, 20, True),
        ("Queen Bed Frame", 203.2, 152.4, False),  # cm listings are already inches
    ],
)
def test_title_size_mismatch_boundaries(
    title: str, along: float, across: float, bad: bool
) -> None:
    assert title_size_mismatch(title, along, across) is bad


def test_title_size_mismatch_degenerate_inputs() -> None:
    assert title_size_mismatch("", 1, 1) is False
    assert title_size_mismatch("Queen", 1, 1) is False  # no "bed" word
    assert title_size_mismatch("Queen Bed Frame", 0, 0) is True


def test_cm_listing_is_converted_before_the_size_check() -> None:
    ok = parse_product(raw("Frame 205 x 155 cm", title="Queen Bed Frame"))
    assert ok and ok.dimension_confidence == "stated"
    bad = parse_product(raw("Frame 205 x 100 cm", title="Queen Bed Frame"))
    assert bad and bad.dimension_reason == "size_mismatch"


# ---------- rotation ----------

WALLS = ("top", "bottom", "left", "right")


def rand_room(rng: random.Random, wall: str) -> dict[str, Any]:
    w, d = rng.randint(100, 200), rng.randint(100, 200)
    return {
        "width": w,
        "depth": d,
        "door": {"wall": wall, "offset": 8, "width": 32, "swing": "in"},
    }


def dims_of(p: Product) -> tuple[float, float]:
    assert p.dimensions
    return p.dimensions.w, p.dimensions.d


def check_response(room: dict[str, Any], body: dict[str, Any], layout: list[Any]) -> None:
    by_slot = {i["slot_id"]: i["product"]["dimensions"] for i in layout}
    reported = any(f["rule"] == "outside_room" for f in body["evaluation"]["hard_fails"])
    for role, r in body["placed"].items():
        inside = (
            r["x"] >= -1e-6
            and r["y"] >= -1e-6
            and r["x"] + r["w"] <= room["width"] + 1e-6
            and r["y"] + r["d"] <= room["depth"] + 1e-6
        )
        assert inside or reported  # outside the room is only allowed if it is reported
        d = by_slot.get(role)
        if d:
            assert sorted((r["w"], r["d"])) == pytest.approx(sorted((d["w"], d["d"])))
            square = d["w"] == d["d"]
            if square:
                assert role not in body["rotated"]
    assert set(body["rotated"]) <= set(body["placed"])


def test_rotation_property_recommend_and_evaluate() -> None:
    rng = random.Random(1234)
    for n in range(60):
        room = rand_room(rng, WALLS[n % 4])
        def sizes() -> tuple[float, float]:
            return rng.randint(15, 90), rng.randint(15, 90)

        use(
            FakeCatalog(
                {
                    "desk chair": [product("c", 40, None)],
                    "bed": [product("b", 100, (rng.randint(70, 90), rng.randint(36, 80)))],
                    "nightstand": [product("n", 10, sizes())],
                    "dresser": [product("r", 20, sizes())],
                    "desk": [product("d", 30, sizes())],
                }
            )
        )
        rec = client.post("/api/recommend", json={"room": room})
        assert rec.status_code == 200, rec.text
        body = rec.json()
        check_response(room, body, body["layout"])
        assert not any(f["rule"] == "outside_room" for f in body["evaluation"]["hard_fails"])
        baseline = client.post("/api/evaluate", json={"room": room, "layout": []}).json()
        base_fails = {(f["rule"], tuple(f["pieces"])): f["short_in"] for f in baseline["evaluation"]["hard_fails"]}
        for f in body["evaluation"]["hard_fails"]:
            k = (f["rule"], tuple(f["pieces"]))
            assert k in base_fails and f["short_in"] <= base_fails[k] + 1e-6

        layout = body["layout"]
        score = {}
        for choice in (None, True, False):
            items = [
                {**i, "rotated": choice} if i["slot_id"] != "desk_chair" else i
                for i in layout
            ]
            ev = client.post("/api/evaluate", json={"room": room, "layout": items})
            assert ev.status_code == 200
            e = ev.json()
            check_response(room, e, items)
            fails = e["evaluation"]["hard_fails"]
            score[choice] = (len(fails), sum(f["short_in"] for f in fails))
            if choice is False:
                assert e["rotated"] == []
        assert score[None] <= min(score[True], score[False])


def test_explicit_rotated_on_unplaceable_item() -> None:
    p = product("x", 10, None)
    for rot in (True, False, None):
        r = client.post(
            "/api/evaluate",
            json={"room": ROOM, "layout": [{"slot_id": "dresser", "product": p.model_dump(), "rotated": rot}]},
        )
        assert r.status_code == 200
        b = r.json()
        assert [u["slot_id"] for u in b["unplaced"]] == ["dresser"]
        assert b["rotated"] == [] and "dresser" not in b["placed"]


def test_square_piece_is_never_rotated() -> None:
    p = product("sq", 10, (30, 30))
    r = client.post(
        "/api/evaluate",
        json={"room": ROOM, "layout": [{"slot_id": "dresser", "product": p.model_dump(), "rotated": True}]},
    ).json()
    assert r["rotated"] == []


def test_duplicate_slots_are_rejected_whatever_the_rotation() -> None:
    it = {"slot_id": "desk", "product": product("a", 1, (48, 24)).model_dump()}
    r = client.post(
        "/api/evaluate",
        json={"room": ROOM, "layout": [it, {**it, "rotated": True}]},
    )
    assert r.status_code == 422


def test_evaluate_rotated_flag_roundtrip_matches_response() -> None:
    p = product("d", 50, (60, 30))
    out = client.post(
        "/api/evaluate",
        json={"room": ROOM, "layout": [{"slot_id": "dresser", "product": p.model_dump(), "rotated": True}]},
    ).json()
    assert out["rotated"] == ["dresser"]


# ---------- counts ----------


def test_counts_sum_to_found_and_usable_is_stated_plus_inferred() -> None:
    def prod(pid: str, conf: str, dims: tuple[float, float] | None) -> Product:
        return product(pid, 10, dims).model_copy(update={"dimension_confidence": conf})

    items = [
        prod("a", "stated", (48, 24)),
        prod("b", "inferred", (50, 24)),
        prod("c", "ambiguous", None),
        prod("d", "missing", None),
        prod("e", "missing", None),
    ]
    use(FakeCatalog({"desk chair": [], "desk": items}))
    s = client.post("/api/recommend", json={"room": ROOM}).json()["searched"]["desk"]
    assert s["stated"] + s["inferred"] + s["ambiguous"] + s["missing"] == s["found"] == 5
    assert s["with_dimensions"] == s["stated"] + s["inferred"] == 2


def test_empty_search_counts_are_zero() -> None:
    use(FakeCatalog({}))
    r = client.post("/api/recommend", json={"room": ROOM}).json()
    for s in r["searched"].values():
        assert s["found"] == 0
        assert (s["stated"], s["inferred"], s["ambiguous"], s["missing"]) == (0, 0, 0, 0)


def test_bed_step_down_with_mixed_confidence() -> None:
    def prod(pid: str, conf: str, dims: tuple[float, float] | None, title: str) -> Product:
        return product(pid, 10, dims, title).model_copy(update={"dimension_confidence": conf})

    use(
        FakeCatalog(
            {
                "King": [prod("k", "ambiguous", None, "King Bed Frame")],
                "Queen": [prod("q1", "inferred", (84, 62), "Queen Bed Frame"), prod("q2", "missing", None, "Queen")],
                "Full": [prod("f", "stated", (79, 58), "Full Bed Frame")],
                "bed": [prod("any", "stated", (84, 62), "Queen Bed Frame")],
            }
        )
    )
    r = client.post("/api/recommend", json={"room": ROOM})
    assert r.status_code == 200
    b = r.json()
    s = b["searched"]["bed"]
    assert s["stated"] + s["inferred"] + s["ambiguous"] + s["missing"] == s["found"]
    if b["bed_size"] is None:
        assert not any(i["slot_id"] == "bed" for i in b["layout"])
