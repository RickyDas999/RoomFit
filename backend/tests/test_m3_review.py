"""Regression tests for the M3 review findings."""

import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient
from test_api_fit import BED, CATALOG, ROOM, FakeCatalog, layout_item, product

from app.catalog import CatalogClient, CatalogError, Product
from app.dimensions import Dimensions
from app.fit import Footprints, evaluate_layout, orient
from app.main import app, get_catalog
from app.room import SAMPLE_ROOM, Rect, plan_room

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean() -> None:
    app.dependency_overrides.clear()
    get_catalog.cache_clear()


# --- the catalog failing for any reason is a 502, never a 500 ---


def test_missing_credentials_is_a_502(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SHOPIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SHOPIFY_CLIENT_SECRET", raising=False)
    r = client.post("/api/recommend", json={"room": ROOM})
    assert r.status_code == 502
    assert (
        "SHOPIFY_CLIENT_ID" in r.json()["detail"]
    )  # names the variable, never a value


@pytest.mark.parametrize(
    "exc", [httpx.ConnectTimeout("t"), httpx.ConnectError("c"), httpx.ReadError("r")]
)
def test_network_errors_become_catalog_errors(exc: Exception) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(CatalogError, match="network error"):
        asyncio.run(CatalogClient("id", "secret", http=http).search("desk"))


def test_network_error_message_has_no_secrets_or_urls() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(
            "could not reach https://api.shopify.com with secret-xyz"
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(CatalogError) as e:
        asyncio.run(CatalogClient("id", "secret-xyz", http=http).search("desk"))
    assert "secret-xyz" not in str(e.value) and "shopify" not in str(e.value)


# --- closet front follows the closet's own orientation ---


def closet_dir(x: float, y: float, w: float, d: float) -> str:
    room = SAMPLE_ROOM.model_copy(update={"closet": Rect(x=x, y=y, w=w, d=d)})
    return plan_room(room).closet_front_dir


@pytest.mark.parametrize(
    ("rect", "direction"),
    [
        ((0, 0, 48, 24), "+y"),  # wide, top wall
        ((0, 0, 24, 48), "+x"),  # tall, top-left corner: a left-wall closet
        ((120, 0, 24, 48), "-x"),  # tall, top-right corner
        ((0, 168, 48, 24), "-y"),  # wide, bottom wall
        ((0, 60, 24, 48), "+x"),  # left wall
        ((120, 60, 24, 48), "-x"),  # right wall
    ],
)
def test_closet_front_direction(
    rect: tuple[float, float, float, float], direction: str
) -> None:
    assert closet_dir(*rect) == direction


# --- /api/evaluate details ---


def test_duplicate_chair_items_are_rejected() -> None:
    p = product("c", 10, None)
    body = {
        "room": ROOM,
        "layout": [layout_item("desk_chair", p), layout_item("desk_chair", p)],
    }
    assert client.post("/api/evaluate", json=body).status_code == 422


def test_bad_layout_names_the_exact_rules_that_break() -> None:
    # a corner desk 72 x 72 next to a 40 in bed: the chair backs into the bed and takes its open side
    layout: Footprints = {"bed": (80, 40), "desk": orient(Dimensions(w=72, d=72))}
    _, _, ev = evaluate_layout(SAMPLE_ROOM, layout)
    assert {f.rule: f.short_in for f in ev.hard_fails} == {
        "behind_desk_chair": 6,
        "bed_open_side": 12,
    }


def test_realistic_oversized_listing_goes_through_orient() -> None:
    # a 70 x 75 in L-shaped desk listing: long side 75 along the wall, 70 deep
    layout: Footprints = {"bed": (80, 40), "desk": orient(Dimensions(w=70, d=75))}
    _, placed, ev = evaluate_layout(SAMPLE_ROOM, layout)
    assert placed["desk"].w == 70 and placed["desk"].d == 75
    assert "behind the desk chair: 4 in short" in [f.message for f in ev.hard_fails]
    # ...while a 66 in deep desk leaves exactly 18 in behind the chair, so that rule passes
    # (the chair still takes the bed's open side, which is its own rule)
    edge: Footprints = {"bed": (80, 40), "desk": (70, 66)}
    rules = {f.rule for f in evaluate_layout(SAMPLE_ROOM, edge)[2].hard_fails}
    assert "behind_desk_chair" not in rules and "bed_open_side" in rules


def test_very_short_desk_keeps_its_chair_inside_the_room() -> None:
    _, placed, ev = evaluate_layout(SAMPLE_ROOM, {"desk": (12, 6)})
    chair = placed["desk_chair"]
    assert 0 <= chair.y and chair.y + chair.d <= 192
    assert not any(f.rule == "outside_room" for f in ev.hard_fails)


# --- /api/recommend details ---


def test_recommend_tie_on_price_and_title_is_broken_by_id() -> None:
    a = product("a", 100, BED, "same title")
    b = product("b", 100, BED, "same title")
    for order in ([a, b], [b, a]):
        app.dependency_overrides[get_catalog] = lambda order=order: FakeCatalog(
            {**CATALOG, "bed frame": order}
        )
        body = client.post("/api/recommend", json={"room": ROOM}).json()
        assert next(i for i in body["layout"] if i["slot_id"] == "bed")["product"][
            "id"
        ].endswith("/a")


def test_recommend_does_not_accept_a_candidate_that_worsens_an_existing_fail() -> None:
    # closet pushed into the lane: "closet" is already in the path before any furniture
    room = {**ROOM, "closet": {"x": 60, "y": 0, "w": 40, "d": 24}}
    app.dependency_overrides[get_catalog] = lambda: FakeCatalog(CATALOG)
    body = client.post("/api/recommend", json={"room": room}).json()
    base = {f["rule"] for f in body["evaluation"]["hard_fails"]}
    assert (
        "path_from_door" in base
    )  # the room itself is the problem, and it is reported
    fails = [
        f for f in body["evaluation"]["hard_fails"] if f["rule"] != "path_from_door"
    ]
    assert fails == [] or all(f["pieces"] == ["closet"] for f in fails)


def test_product_fixture_type() -> None:
    assert isinstance(product("x", 1, (10, 10)), Product)
