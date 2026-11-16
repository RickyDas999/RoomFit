"""API tests for /api/evaluate and /api/recommend, with a fake catalog (no network)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.catalog import CatalogError, Price, Product, Shop
from app.dimensions import Dimensions
from app.main import app, get_catalog
from app.room import SAMPLE_ROOM

ROOM = SAMPLE_ROOM.model_dump()


def product(
    pid: str,
    price: int,
    dims: tuple[float, float] | None,
    title: str = "",
    shop: str = "s1",
) -> Product:
    """Synthetic listing (made up, not Shopify data)."""
    return Product(
        id=f"gid://shopify/p/{pid}",
        variant_id=f"gid://shopify/ProductVariant/{pid}",
        title=title or f"item {pid}",
        shop=Shop(id=shop, name=shop, domain=f"{shop}.example"),
        price=Price(amount=price, currency="USD"),
        image_url=None,
        url=None,
        native_checkout=True,
        description="",
        dimensions=Dimensions(w=dims[0], d=dims[1]) if dims else None,
        dimension_status="parsed" if dims else "missing",
        dimension_confidence="stated" if dims else "missing",
    )


class FakeCatalog:
    def __init__(self, by_query: dict[str, list[Product]], fail: bool = False) -> None:
        self.by_query, self.fail, self.queries = by_query, fail, []

    async def search(self, query: str, limit: int = 25) -> list[Product]:
        self.queries.append(query)
        if self.fail:
            raise CatalogError("rate limited (HTTP 429) after retries")
        for key, items in self.by_query.items():
            if key in query:
                return items
        return []

    queries: list[str]


def use(fake: FakeCatalog) -> None:
    app.dependency_overrides[get_catalog] = lambda: fake


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    yield
    app.dependency_overrides.clear()


client = TestClient(app)

BED = (
    81.4,
    40.1,
)  # listed as length x width: orient() puts the long side along the wall


def layout_item(slot: str, p: Product) -> dict[str, object]:
    return {"slot_id": slot, "product": p.model_dump()}


# --- /api/evaluate ---


def test_evaluate_good_layout() -> None:
    layout = [
        layout_item("bed", product("b", 100, BED)),
        layout_item("desk", product("d", 100, (48, 24))),
        layout_item("dresser", product("r", 100, (36, 20))),
    ]
    r = client.post("/api/evaluate", json={"room": ROOM, "layout": layout})
    assert r.status_code == 200
    body = r.json()
    assert body["evaluation"]["verdict"] == "fits"
    assert set(body["placed"]) == {"bed", "desk", "desk_chair", "dresser"}
    assert [s["id"] for s in body["slots"]] == [
        "bed",
        "desk",
        "desk_chair",
        "dresser",
        "nightstand",
    ]


def test_evaluate_oversized_desk_swap_names_the_rule_and_inches() -> None:
    layout = [
        layout_item("bed", product("b", 100, (80, 40))),
        layout_item("desk", product("d", 100, (72, 72))),  # a deep corner desk
    ]
    ev = client.post("/api/evaluate", json={"room": ROOM, "layout": layout}).json()[
        "evaluation"
    ]
    by_rule = {f["rule"]: f for f in ev["hard_fails"]}
    assert by_rule["behind_desk_chair"]["short_in"] == 6
    assert (
        by_rule["behind_desk_chair"]["message"] == "behind the desk chair: 6 in short"
    )
    assert ev["verdict"] == "cramped"


def test_evaluate_product_without_dimensions_cannot_be_placed() -> None:
    layout = [layout_item("bed", product("b", 100, None))]
    body = client.post("/api/evaluate", json={"room": ROOM, "layout": layout}).json()
    assert body["placed"] == {}
    assert body["unplaced"] == [{"slot_id": "bed", "reason": "dimensions missing"}]
    assert "sleep" in body["evaluation"]["missing_needs"]


def test_evaluate_chair_item_is_ignored_for_geometry() -> None:
    layout = [
        layout_item("desk", product("d", 100, (48, 24))),
        layout_item("desk_chair", product("c", 100, (60, 60))),  # real size is not used
    ]
    body = client.post("/api/evaluate", json={"room": ROOM, "layout": layout}).json()
    chair = body["placed"]["desk_chair"]
    assert chair["w"] == chair["d"] == 20


def test_evaluate_rejects_duplicate_slots_and_bad_rooms() -> None:
    p = product("b", 100, BED)
    dup = {"room": ROOM, "layout": [layout_item("bed", p), layout_item("bed", p)]}
    assert client.post("/api/evaluate", json=dup).status_code == 422
    bad_room = {**ROOM, "door": {"wall": "top", "offset": 140, "width": 32}}
    assert (
        client.post("/api/evaluate", json={"room": bad_room, "layout": []}).status_code
        == 422
    )
    unknown = {"room": ROOM, "layout": [{"slot_id": "sofa", "product": p.model_dump()}]}
    assert client.post("/api/evaluate", json=unknown).status_code == 422


def test_evaluate_works_for_a_room_with_the_door_on_another_wall() -> None:
    room = {
        "width": 192,
        "depth": 144,
        "door": {"wall": "left", "offset": 56, "width": 32},
        "closet": {"x": 0, "y": 0, "w": 24, "d": 48},
    }
    layout = [
        layout_item("bed", product("b", 100, BED)),
        layout_item("desk", product("d", 100, (48, 24))),
    ]
    body = client.post("/api/evaluate", json={"room": room, "layout": layout}).json()
    assert body["evaluation"]["hard_fails"] == []
    for rect in body[
        "placed"
    ].values():  # placed rects are in this room's own coordinates
        assert 0 <= rect["x"] and rect["x"] + rect["w"] <= 192
        assert 0 <= rect["y"] and rect["y"] + rect["d"] <= 144


# --- /api/recommend ---

CATALOG = {
    "bed frame": [
        product("bed-nodims", 50, None, "cheapest but no size"),
        product("bed-pricey", 300, BED),
        product("bed-cheap", 120, (80.5, 39)),
        product("bed-toowide", 90, (80, 70), "too wide for the slot"),
    ],
    "nightstand": [
        product("ns-1", 40, (18, 16)),
        product(
            "ns-2", 20, (22, 21), "cheapest, tall enough to reach the chair's back zone"
        ),
    ],
    "dresser": [product("dr-1", 200, (36, 20)), product("dr-2", 150, (40, 18))],
    "desk chair": [product("ch-2", 90, None), product("ch-1", 60, None)],
    "desk": [
        product("desk-huge", 10, (110, 30), "cheapest but too long for the 96 in slot"),
        product(
            "desk-deep",
            30,
            (60, 52),
            "fits the slot but leaves no room behind the chair",
        ),
        product("desk-ok", 80, (48, 24)),
        product("desk-ok2", 60, (47, 24)),
    ],
}


def test_recommend_picks_the_cheapest_that_fits_each_slot() -> None:
    fake = FakeCatalog(CATALOG)
    use(fake)
    body = client.post("/api/recommend", json={"room": ROOM}).json()
    chosen = {i["slot_id"]: i["product"]["id"].split("/")[-1] for i in body["layout"]}
    assert (
        chosen["bed"] == "bed-cheap"
    )  # skips no-dimensions and too-wide, cheaper than bed-pricey
    assert chosen["nightstand"] == "ns-2"
    assert chosen["dresser"] == "dr-2"
    assert chosen["desk"] == "desk-ok2"
    assert body["sorted_by"] == "lowest price that fits"
    assert body["evaluation"]["verdict"] == "fits"
    assert body["unplaced"] == []


def test_recommend_rejects_a_cheap_desk_that_breaks_a_rule() -> None:
    use(FakeCatalog(CATALOG))
    body = client.post("/api/recommend", json={"room": ROOM}).json()
    ids = [i["product"]["id"] for i in body["layout"]]
    assert (
        "gid://shopify/p/desk-deep" not in ids
    )  # 52 in deep: chair clearance fails next to the nightstand
    assert "gid://shopify/p/desk-huge" not in ids  # does not fit the slot at all


def test_recommend_chair_is_the_cheapest_and_its_size_is_marked_assumed() -> None:
    use(FakeCatalog(CATALOG))
    body = client.post("/api/recommend", json={"room": ROOM}).json()
    chair = next(i for i in body["layout"] if i["slot_id"] == "desk_chair")
    assert chair["product"]["id"].endswith("ch-1")
    assert chair["footprint_basis"] == "assumed"
    assert body["placed"]["desk_chair"]["w"] == 20


def test_recommend_reports_search_stats() -> None:
    use(FakeCatalog(CATALOG))
    stats = client.post("/api/recommend", json={"room": ROOM}).json()["searched"]
    assert stats["bed"] == {
        "found": 4, "with_dimensions": 3, "fit_slot": 2,
        "stated": 3, "inferred": 0, "ambiguous": 0, "missing": 1,
    }
    assert stats["desk"] == {
        "found": 4, "with_dimensions": 4, "fit_slot": 3,
        "stated": 4, "inferred": 0, "ambiguous": 0, "missing": 0,
    }
    assert stats["desk_chair"]["with_dimensions"] == 0


def test_recommend_says_so_when_nothing_fits() -> None:
    use(
        FakeCatalog(
            {
                **CATALOG,
                "desk": [product("desk-huge", 10, (110, 30)), product("d0", 5, None)],
            }
        )
    )
    body = client.post("/api/recommend", json={"room": ROOM}).json()
    assert {"slot_id": "desk", "reason": "no desk fits under these rules"} in body[
        "unplaced"
    ]
    assert "desk_chair" not in {i["slot_id"] for i in body["layout"]}
    assert "study" in body["evaluation"]["missing_needs"]
    assert body["evaluation"]["verdict"] == "incomplete"


def test_recommend_says_so_when_no_listing_has_dimensions() -> None:
    use(FakeCatalog({**CATALOG, "dresser": [product("d0", 5, None)]}))
    body = client.post("/api/recommend", json={"room": ROOM}).json()
    assert {
        "slot_id": "dresser",
        "reason": "no listing with usable dimensions",
    } in body["unplaced"]


def test_recommend_slot_with_no_space_is_not_searched() -> None:
    room = {
        **ROOM,
        "width": 40,
        "depth": 50,
        "door": {"wall": "top", "offset": 4, "width": 32},
        "closet": None,
        "window": None,
    }
    fake = FakeCatalog(CATALOG)
    use(fake)
    body = client.post("/api/recommend", json={"room": room}).json()
    assert not any("desk" in q for q in fake.queries)
    assert {"slot_id": "desk", "reason": "no desk fits under these rules"} in body[
        "unplaced"
    ]


def test_recommend_catalog_failure_is_a_502_without_secrets() -> None:
    use(FakeCatalog(CATALOG, fail=True))
    r = client.post("/api/recommend", json={"room": ROOM})
    assert r.status_code == 502
    assert "429" in r.json()["detail"]


def test_recommend_is_deterministic() -> None:
    use(FakeCatalog(CATALOG))
    a = client.post("/api/recommend", json={"room": ROOM}).json()
    b = client.post("/api/recommend", json={"room": ROOM}).json()
    assert a == b


def test_recommend_queries_use_slot_sizes_with_the_search_cap() -> None:
    fake = FakeCatalog(CATALOG)
    use(fake)
    client.post("/api/recommend", json={"room": ROOM})
    assert sorted(fake.queries) == sorted(
        [
            "twin xl bed frame",
            "desk 60 inch",
            "desk chair",
            "dresser 48 inch",
            "nightstand",
        ]
    )


# --- guardrails ---


def test_checkout_completion_does_not_exist_anywhere() -> None:
    root = Path(__file__).resolve().parents[2]
    needle = "complete_" + "checkout"  # split so this file does not contain the word
    for path in [
        *root.glob("backend/app/**/*.py"),
        *root.glob("frontend/src/**/*.ts*"),
    ]:
        assert needle not in path.read_text(), path


def test_fit_modules_write_no_files() -> None:
    root = Path(__file__).resolve().parents[1] / "app"
    for name in ("fit.py", "room.py", "rules.py", "main.py"):
        src = (root / name).read_text()
        for banned in (
            "open(",
            "write_text",
            "write_bytes",
            "sqlite",
            "shelve",
            "pickle",
        ):
            assert banned not in src, (name, banned)
