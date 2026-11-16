"""Carts per merchant: request shape, grouping, safety checks, errors, cancel. Mocked HTTP only."""

import json
import logging
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from test_api_fit import product

from app.cart import CartClient, valid_shop_domain
from app.catalog import Shop
from app.main import app, get_cart_client

PROFILE = "https://profile.example/ucp.json"
CART_ID = "gid://shopify/Cart/c1-abc?key=k1"
CONTINUE = "https://shop-a.example.com/cart/c/c1-abc?key=k1"


def cart_reply(over: dict[str, Any] | None = None) -> dict[str, Any]:
    cart: dict[str, Any] = {
        "id": CART_ID,
        "currency": "USD",
        "line_items": [
            {
                "quantity": 1,
                "item": {"id": "x", "title": "Nightstand", "price": 5300},
                "totals": [
                    {"type": "subtotal", "amount": 5300},
                    {"type": "total", "amount": 5300},
                ],
            }
        ],
        "totals": [
            {"type": "subtotal", "amount": 5300, "display_text": "Subtotal"},
            {"type": "total", "amount": 5300, "display_text": "Total"},
        ],
        "messages": [],
        "continue_url": CONTINUE,
    }
    cart.update(over or {})
    return {"jsonrpc": "2.0", "id": 1, "result": {"structuredContent": cart}}


class Shops:
    """Mock merchants: records every request, answers with `handler` (default: a cart)."""

    def __init__(
        self,
        handler: Callable[[httpx.Request, dict[str, Any]], httpx.Response]
        | None = None,
    ) -> None:
        self.requests: list[httpx.Request] = []
        self.bodies: list[dict[str, Any]] = []
        self.handler = handler or (lambda r, b: httpx.Response(200, json=cart_reply()))

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(request)
        self.bodies.append(body)
        return self.handler(request, body)

    def client(self) -> CartClient:
        return CartClient(
            PROFILE, httpx.AsyncClient(transport=httpx.MockTransport(self))
        )


def listing(
    pid: str, domain: str, variant: str | None = None, shop_id: str | None = None
) -> dict[str, Any]:
    p = product(pid, 5300, (40, 20)).model_copy(
        update={
            "variant_id": variant
            or f"gid://shopify/ProductVariant/{abs(hash(pid)) % 10**9}",
            "shop": Shop(
                id=shop_id or f"gid://shopify/Shop/{domain}", name=domain, domain=domain
            ),
        }
    )
    return {"slot_id": "nightstand", "product": p.model_dump()}


@pytest.fixture
def api() -> Iterator[Callable[[Shops], TestClient]]:
    def use(shops: Shops) -> TestClient:
        c = shops.client()
        app.dependency_overrides[get_cart_client] = lambda: c
        return TestClient(app)

    yield use
    app.dependency_overrides.clear()


# ---------- request shape ----------


def test_create_cart_request_shape_is_anonymous_and_names_our_profile(
    api: Callable[[Shops], TestClient],
) -> None:
    shops = Shops()
    item = listing("a", "shop-a.example.com", "gid://shopify/ProductVariant/111")
    res = api(shops).post("/api/checkout", json={"layout": [item]})
    assert res.status_code == 200
    (req,), (body,) = shops.requests, shops.bodies
    assert str(req.url) == "https://shop-a.example.com/api/ucp/mcp"
    assert body["method"] == "tools/call" and body["params"]["name"] == "create_cart"
    args = body["params"]["arguments"]
    assert args["meta"] == {"ucp-agent": {"profile": PROFILE}}
    assert args["cart"]["line_items"] == [
        {"quantity": 1, "item": {"id": "gid://shopify/ProductVariant/111"}}
    ]
    # no token and no buyer IP: carts are anonymous, so the user's IP is never sent
    assert "authorization" not in req.headers
    assert not any("ip" in k.lower() for k in req.headers)


def test_the_session_shows_what_the_merchant_returned(
    api: Callable[[Shops], TestClient],
) -> None:
    res = (
        api(Shops())
        .post("/api/checkout", json={"layout": [listing("a", "shop-a.example.com")]})
        .json()
    )
    assert res["notice"] == "Prototype: purchase disabled"
    (s,) = res["sessions"]
    assert (
        s["status"] == "created" and s["cart_id"] == CART_ID and s["currency"] == "USD"
    )
    assert s["lines"] == [{"title": "Nightstand", "quantity": 1, "amount": 5300}]
    assert {t["type"]: t["amount"] for t in s["totals"]} == {
        "subtotal": 5300,
        "total": 5300,
    }
    assert s["continue_url"] == CONTINUE and s["shop"]["domain"] == "shop-a.example.com"


# ---------- grouping ----------


def test_one_cart_per_merchant_with_each_merchants_items(
    api: Callable[[Shops], TestClient],
) -> None:
    shops = Shops()
    layout = [
        listing("a", "shop-a.example.com", "gid://shopify/ProductVariant/1"),
        listing("b", "shop-b.example.com", "gid://shopify/ProductVariant/2"),
        listing("c", "shop-a.example.com", "gid://shopify/ProductVariant/3"),
    ]
    res = api(shops).post("/api/checkout", json={"layout": layout}).json()
    assert [s["shop"]["domain"] for s in res["sessions"]] == [
        "shop-a.example.com",
        "shop-b.example.com",
    ]
    by_host = {
        r.url.host: b["params"]["arguments"]["cart"]["line_items"]
        for r, b in zip(shops.requests, shops.bodies, strict=True)
    }
    assert [li["item"]["id"] for li in by_host["shop-a.example.com"]] == [
        "gid://shopify/ProductVariant/1",
        "gid://shopify/ProductVariant/3",
    ]
    assert [li["item"]["id"] for li in by_host["shop-b.example.com"]] == [
        "gid://shopify/ProductVariant/2"
    ]


def test_the_same_variant_twice_becomes_quantity_two_and_domain_case_does_not_split_a_shop(
    api: Callable[[Shops], TestClient],
) -> None:
    shops = Shops()
    v = "gid://shopify/ProductVariant/7"
    layout = [
        listing("a", "Shop-A.example.com", v),
        listing("b", "shop-a.example.com", v),
    ]
    api(shops).post("/api/checkout", json={"layout": layout})
    assert len(shops.requests) == 1
    assert shops.bodies[0]["params"]["arguments"]["cart"]["line_items"] == [
        {"quantity": 2, "item": {"id": v}}
    ]


def test_nothing_to_buy_makes_no_calls_and_too_many_merchants_is_refused(
    api: Callable[[Shops], TestClient],
) -> None:
    shops = Shops()
    client = api(shops)
    assert client.post("/api/checkout", json={"layout": []}).json()["sessions"] == []
    many = [listing(f"p{i}", f"shop-{i}.example.com") for i in range(11)]
    assert client.post("/api/checkout", json={"layout": many}).status_code == 422
    assert shops.requests == []


# ---------- safety: the browser supplies the shop address, the server calls it ----------


@pytest.mark.parametrize(
    "domain",
    [
        "localhost",
        "127.0.0.1",
        "10.0.0.5",
        "169.254.169.254",
        "shop.local",
        "x.internal",
        "a.example.com:8080",
        "a.example.com/path",
        "user@a.example.com",
        "https://a.example.com",
        "",
        " ",
        "a",
        "-a.example.com",
        "a..com",
        "[::1]",
        "shop.example.com\\evil.com",
        "a.example.com?x=1",
    ],
)
def test_unsafe_shop_addresses_are_never_called(
    domain: str, api: Callable[[Shops], TestClient]
) -> None:
    shops = Shops()
    res = (
        api(shops).post("/api/checkout", json={"layout": [listing("a", domain)]}).json()
    )
    assert shops.requests == []
    assert res["sessions"][0]["status"] == "error"


@pytest.mark.parametrize(
    "domain", ["shop-a.example.com", "91f95a-70.myshopify.com", "a.b.c.example.co.uk"]
)
def test_normal_shop_addresses_pass(domain: str) -> None:
    assert valid_shop_domain(domain)


@pytest.mark.parametrize(
    "variant",
    [
        "",
        "1234",
        "gid://shopify/Product/1",
        "gid://shopify/ProductVariant/abc",
        "gid://shopify/ProductVariant/1/../x",
    ],
)
def test_odd_variant_ids_are_never_sent(
    variant: str, api: Callable[[Shops], TestClient]
) -> None:
    shops = Shops()
    res = (
        api(shops)
        .post(
            "/api/checkout",
            json={"layout": [listing("a", "shop-a.example.com", variant)]},
        )
        .json()
    )
    assert shops.requests == [] and res["sessions"][0]["status"] == "error"


@pytest.mark.parametrize(
    "url",
    [
        "http://shop.example.com/c",
        "javascript:alert(1)",
        "//shop.example.com/c",
        "ftp://x/y",
        7,
        None,
        "",
    ],
)
def test_a_continue_link_that_is_not_https_is_dropped(
    url: object, api: Callable[[Shops], TestClient]
) -> None:
    shops = Shops(
        lambda r, b: httpx.Response(200, json=cart_reply({"continue_url": url}))
    )
    (s,) = (
        api(shops)
        .post("/api/checkout", json={"layout": [listing("a", "shop-a.example.com")]})
        .json()["sessions"]
    )
    assert s["status"] == "created" and s["continue_url"] is None


def test_the_continue_link_is_never_logged(
    api: Callable[[Shops], TestClient], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    api(Shops()).post(
        "/api/checkout", json={"layout": [listing("a", "shop-a.example.com")]}
    )
    assert CONTINUE not in caplog.text and "key=k1" not in caplog.text


# ---------- errors: one shop failing never takes the others down ----------


def test_one_failing_shop_does_not_fail_the_others(
    api: Callable[[Shops], TestClient],
) -> None:
    def handler(r: httpx.Request, b: dict[str, Any]) -> httpx.Response:
        return (
            httpx.Response(500)
            if r.url.host == "shop-b.example.com"
            else httpx.Response(200, json=cart_reply())
        )

    res = (
        api(Shops(handler))
        .post(
            "/api/checkout",
            json={
                "layout": [
                    listing("a", "shop-a.example.com"),
                    listing("b", "shop-b.example.com"),
                ]
            },
        )
        .json()
    )
    assert [s["status"] for s in res["sessions"]] == ["created", "error"]
    assert "HTTP 500" in res["sessions"][1]["error"]


@pytest.mark.parametrize(
    ("make", "text"),
    [
        (lambda: httpx.Response(429), "rate limiting"),
        (lambda: httpx.Response(200, text="<html>"), "not JSON"),
        (lambda: httpx.Response(200, json=[1]), "not a JSON object"),
        (
            lambda: httpx.Response(200, json={"error": {"message": "Unauthorized"}}),
            "Unauthorized",
        ),
        (lambda: httpx.Response(200, json={"result": {}}), "no cart"),
        (lambda: httpx.Response(200, json=cart_reply({"id": "nope"})), "no cart"),
        (
            lambda: httpx.Response(
                200,
                json=cart_reply(
                    {
                        "id": None,
                        "messages": [
                            {"type": "error", "code": "x", "content": "out of stock"}
                        ],
                    }
                ),
            ),
            "out of stock",
        ),
    ],
)
def test_bad_shop_answers_become_an_error_session(
    make: Callable[[], httpx.Response], text: str, api: Callable[[Shops], TestClient]
) -> None:
    shops = Shops(lambda r, b: make())
    res = api(shops).post(
        "/api/checkout", json={"layout": [listing("a", "shop-a.example.com")]}
    )
    assert res.status_code == 200
    (s,) = res.json()["sessions"]
    assert s["status"] == "error" and text in s["error"] and s["continue_url"] is None


def test_a_network_failure_is_an_error_session_without_the_address(
    api: Callable[[Shops], TestClient],
) -> None:
    def boom(r: httpx.Request, b: dict[str, Any]) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out talking to shop-a.example.com")

    (s,) = (
        api(Shops(boom))
        .post("/api/checkout", json={"layout": [listing("a", "shop-a.example.com")]})
        .json()["sessions"]
    )
    assert s["status"] == "error" and s["error"] == "network error (ConnectTimeout)"


def test_a_cart_with_warnings_is_kept_with_its_messages(
    api: Callable[[Shops], TestClient],
) -> None:
    msgs = [{"type": "warning", "code": "quantity_adjusted", "content": "Only 1 left"}]
    (s,) = (
        api(
            Shops(lambda r, b: httpx.Response(200, json=cart_reply({"messages": msgs})))
        )
        .post("/api/checkout", json={"layout": [listing("a", "shop-a.example.com")]})
        .json()["sessions"]
    )
    assert s["status"] == "created" and s["messages"] == [
        {"type": "warning", "code": "quantity_adjusted", "content": "Only 1 left"}
    ]


def test_a_weird_cart_body_never_crashes(api: Callable[[Shops], TestClient]) -> None:
    odd = cart_reply(
        {
            "line_items": "x",
            "totals": [1, {"type": 1}, {"type": "total", "amount": "9"}],
            "messages": [None, 3],
        }
    )
    (s,) = (
        api(Shops(lambda r, b: httpx.Response(200, json=odd)))
        .post("/api/checkout", json={"layout": [listing("a", "shop-a.example.com")]})
        .json()["sessions"]
    )
    assert (
        s["status"] == "created"
        and s["lines"] == []
        and s["totals"] == []
        and s["messages"] == []
    )


# ---------- cancel ----------


def test_cancel_sends_an_idempotency_key_and_the_cart_id(
    api: Callable[[Shops], TestClient],
) -> None:
    shops = Shops(lambda r, b: httpx.Response(200, json=cart_reply()))
    res = api(shops).post(
        "/api/checkout/cancel",
        json={"carts": [{"domain": "shop-a.example.com", "cart_id": CART_ID}]},
    )
    assert res.json() == {"cancelled": 1, "failed": 0}
    (body,) = shops.bodies
    assert body["params"]["name"] == "cancel_cart"
    args = body["params"]["arguments"]
    assert args["id"] == CART_ID and args["meta"]["ucp-agent"] == {"profile": PROFILE}
    assert (
        str(uuid.UUID(args["meta"]["idempotency-key"]))
        == args["meta"]["idempotency-key"]
    )


def test_each_cancel_gets_its_own_key_and_failures_are_counted(
    api: Callable[[Shops], TestClient],
) -> None:
    def handler(r: httpx.Request, b: dict[str, Any]) -> httpx.Response:
        return (
            httpx.Response(500)
            if r.url.host == "shop-b.example.com"
            else httpx.Response(200, json=cart_reply())
        )

    shops = Shops(handler)
    carts = [
        {"domain": "shop-a.example.com", "cart_id": CART_ID},
        {"domain": "shop-b.example.com", "cart_id": CART_ID},
        {"domain": "shop-c.example.com", "cart_id": CART_ID},
    ]
    res = api(shops).post("/api/checkout/cancel", json={"carts": carts})
    assert res.json() == {"cancelled": 2, "failed": 1}
    keys = {b["params"]["arguments"]["meta"]["idempotency-key"] for b in shops.bodies}
    assert len(keys) == 3


@pytest.mark.parametrize(
    "ref",
    [
        {"domain": "localhost", "cart_id": CART_ID},
        {"domain": "10.0.0.1", "cart_id": CART_ID},
        {"domain": "shop-a.example.com", "cart_id": "not-a-cart"},
        {"domain": "shop-a.example.com", "cart_id": "gid://shopify/Cart/" + "x" * 500},
    ],
)
def test_cancel_refuses_unsafe_addresses_and_ids_without_calling(
    ref: dict[str, str], api: Callable[[Shops], TestClient]
) -> None:
    shops = Shops()
    res = api(shops).post("/api/checkout/cancel", json={"carts": [ref]})
    assert res.json() == {"cancelled": 0, "failed": 1} and shops.requests == []


def test_cancel_accepts_at_most_ten_carts_and_nothing_is_fine(
    api: Callable[[Shops], TestClient],
) -> None:
    client = api(Shops())
    assert client.post("/api/checkout/cancel", json={"carts": []}).json() == {
        "cancelled": 0,
        "failed": 0,
    }
    eleven = [{"domain": "shop-a.example.com", "cart_id": CART_ID}] * 11
    assert (
        client.post("/api/checkout/cancel", json={"carts": eleven}).status_code == 422
    )


# ---------- guardrails ----------


def test_only_cart_tools_are_ever_called(api: Callable[[Shops], TestClient]) -> None:
    shops = Shops()
    client = api(shops)
    client.post("/api/checkout", json={"layout": [listing("a", "shop-a.example.com")]})
    client.post(
        "/api/checkout/cancel",
        json={"carts": [{"domain": "shop-a.example.com", "cart_id": CART_ID}]},
    )
    assert {b["params"]["name"] for b in shops.bodies} == {"create_cart", "cancel_cart"}
