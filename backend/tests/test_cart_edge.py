"""Adversarial cart tests: SSRF corpus, hostile shop replies, cancel. Mocked HTTP only."""

import asyncio
import json
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from test_cart import CART_ID, Shops, cart_reply, listing

from app.cart import CartClient, create_carts, https_only, valid_shop_domain
from app.catalog import Shop
from app.main import app, get_cart_client

V1 = "gid://shopify/ProductVariant/1"


@pytest.fixture
def api() -> Iterator[Callable[[Shops], TestClient]]:
    def use(shops: Shops) -> TestClient:
        c = shops.client()
        app.dependency_overrides[get_cart_client] = lambda: c
        return TestClient(app)

    yield use
    app.dependency_overrides.clear()


def shop(domain: str = "shop-a.example.com", name: str = "A") -> Shop:
    return Shop(id="gid://shopify/Shop/1", name=name, domain=domain)


def create(
    shops: Shops,
    variants: dict[str, int] | None = None,
    domain: str = "shop-a.example.com",
) -> Any:
    return asyncio.run(shops.client().create(shop(domain), variants or {V1: 1}))


def reply(over: dict[str, Any]) -> Shops:
    return Shops(lambda r, b: httpx.Response(200, json=cart_reply(over)))


# ---------- SSRF corpus ----------

REJECT = [
    "localhost.",
    "LOCALHOST",
    "foo.localhost",
    "foo.localhost.",
    "a.b.local",
    "metadata.google.internal",
    "evil.com#.myshopify.com",
    "evil.com\\.myshopify.com",
    "evil.com%2f.myshopify.com",
    "evil.com%00.myshopify.com",
    "a.example.com\x00",
    "a.example.com\t.evil.com",
    "a.exam\nple.com",
    "shop-a.example.com.",
    "Shop-A.example.com",
    "ѕhop.example.com",
    "shоp.example.com",
    "shop.exаmple.com",
    "ｓｈｏｐ.example.com",
    "shop。example。com",
    "münchen.example.com",
    "shop.example.c0m",
    "shop.example.123",
    "1.2.3.4",
    "2130706433",
    "0x7f000001",
    "0177.0.0.1",
    "127.1",
    "0x7f.1",
    "::1",
    "[::1]",
    "[::ffff:127.0.0.1]",
    "fe80::1",
    "1.2.3.4.5",
    "a.example.com:443",
    "a.example.com@evil.com",
    "evil.com:80@a.example.com",
    "a.example.com/",
    "a.example.com?",
    "a.example.com#",
    "a.example.com ",
    "a_b.example.com",
    "a.example.com,evil.com",
    "a.example.com;evil.com",
    "*.example.com",
    ".example.com",
    "example",
    "a.-b.com",
    "a-.b.com",
    "a.example.com/..",
    "x" * 64 + ".example.com",
    "a." * 130 + "com",
    "a" * 300 + ".com",
    "a.example.x",
    "a.example." + "x" * 64,
    "xn--.com..",
    "a b.example.com",
    "%61.example.com",
]


@pytest.mark.parametrize("domain", REJECT)
def test_hostile_domains_fail_validation(domain: str) -> None:
    # strip() is fine for plain spaces, which the API also strips; everything else must fail
    if domain == "a.example.com ":
        assert valid_shop_domain(domain) in (True, False)
        return
    assert not valid_shop_domain(domain)


@pytest.mark.parametrize("domain", [d for d in REJECT if d.strip() == d])
def test_hostile_domains_make_no_request_even_called_directly(domain: str) -> None:
    shops = Shops()
    s = create(shops, domain=domain)
    assert shops.requests == [] and s.status == "error"
    assert not asyncio.run(shops.client().cancel(domain, CART_ID))
    assert shops.requests == []


@pytest.mark.parametrize(
    "domain", [d for d in REJECT if d.strip() == d and d == d.lower()]
)
def test_hostile_domains_make_no_request_through_the_api(
    domain: str, api: Callable[[Shops], TestClient]
) -> None:
    shops = Shops()
    c = api(shops)
    res = c.post("/api/checkout", json={"layout": [listing("a", domain)]})
    assert res.status_code == 200 and res.json()["sessions"][0]["status"] == "error"
    res = c.post(
        "/api/checkout/cancel", json={"carts": [{"domain": domain, "cart_id": CART_ID}]}
    )
    assert res.json() == {"cancelled": 0, "failed": 1}
    assert shops.requests == []


@pytest.mark.parametrize(
    "domain",
    [
        "a.example.com\n",
        "a.example.com\r\n",
        "\ta.example.com",
    ],
)
def test_surrounding_control_whitespace_is_not_a_valid_domain_for_a_direct_caller(
    domain: str,
) -> None:
    assert not valid_shop_domain(domain)


@pytest.mark.parametrize(
    "domain",
    ["localhost.localdomain", "foo.localdomain", "printer.intranet", "db.private"],
)
def test_more_internal_suffixes_are_blocked(domain: str) -> None:
    assert not valid_shop_domain(domain)


def test_label_and_length_limits() -> None:
    assert valid_shop_domain("a" * 63 + ".example.com")
    assert valid_shop_domain("xn--80ak6aa92e.com")
    assert valid_shop_domain("A".lower() + "b.co")
    assert not valid_shop_domain("a" * 64 + ".example.com")
    assert not valid_shop_domain(("a" * 63 + ".") * 4 + "com")  # > 253 chars


def test_surrounding_spaces_are_stripped_by_the_api_and_the_shop_is_called_clean(
    api: Callable[[Shops], TestClient],
) -> None:
    shops = Shops()
    api(shops).post(
        "/api/checkout", json={"layout": [listing("a", "  Shop-A.Example.com \n")]}
    )
    assert [str(r.url) for r in shops.requests] == [
        "https://shop-a.example.com/api/ucp/mcp"
    ]


# ---------- ids ----------


@pytest.mark.parametrize(
    "cart_id",
    [
        CART_ID + "\r\nX-Evil: 1",
        "gid://shopify/Cart/a b",
        "gid://shopify/Cart/a%0Ab",
        "gid://shopify/Cart/" + "a" * 201,
        "gid://shopify/Cart/",
        "gid://shopify/Cart/a/../b",
        "gid://shopify/Cart/a#b",
        "gid://shopify/Cart/é",
        "gid://shopify/Cart/\x00",
    ],
)
def test_odd_cart_ids_are_never_cancelled(cart_id: str) -> None:
    shops = Shops()
    assert not asyncio.run(shops.client().cancel("shop-a.example.com", cart_id))
    assert shops.requests == []


@pytest.mark.parametrize("variant", [V1 + "\n"])
def test_variant_id_with_trailing_newline_is_never_sent(variant: str) -> None:
    shops = Shops()
    create(shops, {variant: 1})
    assert shops.requests == []


def test_cart_id_trailing_newline_is_never_cancelled() -> None:
    shops = Shops()
    assert not asyncio.run(shops.client().cancel("shop-a.example.com", CART_ID + "\n"))
    assert shops.requests == []


def test_a_cart_reply_with_a_bad_id_is_an_error_not_a_session() -> None:
    for bad in [
        "gid://shopify/Cart/" + "x" * 5000,
        "gid://shopify/Cart/a\nb",
        5,
        None,
        ["x"],
    ]:
        s = create(reply({"id": bad}))
        assert s.status == "error" and s.cart_id is None


def test_errors_never_echo_request_variant_ids(
    api: Callable[[Shops], TestClient],
) -> None:
    secret = "gid://shopify/ProductVariant/<script>999"
    shops = Shops()
    c = api(shops)
    out = c.post(
        "/api/checkout", json={"layout": [listing("a", "shop-a.example.com", secret)]}
    )
    assert "<script>" not in out.text and shops.requests == []
    shops2 = Shops(lambda r, b: httpx.Response(500, text=r.content.decode()))
    out = api(shops2).post(
        "/api/checkout", json={"layout": [listing("a", "shop-a.example.com", V1)]}
    )
    assert V1 not in out.text and "shop-a.example.com/api" not in out.text


# ---------- hostile replies ----------


def test_content_only_result_has_no_cart() -> None:
    s = create(
        Shops(
            lambda r, b: httpx.Response(
                200,
                json={
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(
                                    cart_reply()["result"]["structuredContent"]
                                ),
                            }
                        ]
                    }
                },
            )
        )
    )
    assert s.status == "error" and s.error == "the shop's answer had no cart"


@pytest.mark.parametrize("sc", [[], [{"id": CART_ID}], "x", 5, None, True])
def test_structured_content_that_is_not_an_object(sc: object) -> None:
    s = create(
        Shops(
            lambda r, b: httpx.Response(200, json={"result": {"structuredContent": sc}})
        )
    )
    assert s.status == "error"


def test_is_error_without_a_cart_is_an_error() -> None:
    s = create(
        Shops(
            lambda r, b: httpx.Response(
                200,
                json={
                    "result": {
                        "isError": True,
                        "structuredContent": {
                            "messages": [{"type": "error", "content": "nope"}]
                        },
                    }
                },
            )
        )
    )
    assert s.status == "error" and s.error == "nope"


def test_cart_nested_under_a_cart_key() -> None:
    inner = cart_reply()["result"]["structuredContent"]
    s = create(
        Shops(
            lambda r, b: httpx.Response(
                200, json={"result": {"structuredContent": {"cart": inner}}}
            )
        )
    )
    assert s.status == "created" and s.cart_id == CART_ID


@pytest.mark.parametrize(
    "body",
    [
        {"error": "boom"},
        {"error": {"message": {"x": 1}}},
        {"error": {"message": "m" * 5000}},
        {"error": 5},
        {"error": ["a"]},
    ],
)
def test_jsonrpc_errors_of_any_shape_become_short_errors(body: dict[str, Any]) -> None:
    s = create(Shops(lambda r, b: httpx.Response(200, json=body)))
    assert s.status == "error" and s.error is not None and len(s.error) < 200


@pytest.mark.parametrize("raw", ["[]", "null", "5", '"x"', "not json", "", "{"])
def test_non_object_json_bodies(raw: str) -> None:
    s = create(Shops(lambda r, b: httpx.Response(200, content=raw)))
    assert s.status == "error"


def test_big_fields_are_truncated_and_an_oversized_body_is_refused() -> None:
    big = "x" * 300_000
    s = create(
        reply(
            {
                "messages": [{"type": "warning", "content": big, "code": "c"}],
                "line_items": [{"quantity": 1, "item": {"title": big}}],
                "totals": [{"type": "total", "amount": 1, "display_text": big}],
            }
        )
    )
    assert s.status == "created"
    assert len(s.messages[0].content) <= 300 and len(s.lines[0].title) <= 200
    assert len(s.totals[0].display_text) <= 40
    s = create(reply({"messages": [{"content": "x" * 5_000_000}]}))
    assert s.status == "error" and "too large" in (s.error or "")


def test_deeply_nested_json_does_not_crash() -> None:
    deep = b'{"result":' + b"[" * 100_000 + b"]" * 100_000 + b"}"
    s = create(Shops(lambda r, b: httpx.Response(200, content=deep)))
    assert s.status == "error"


@pytest.mark.parametrize("value", [5, True, "abc", {"a": 1}, [None, 5, "x", [1]]])
def test_totals_of_the_wrong_type_do_not_crash(value: object) -> None:
    assert create(reply({"totals": value})).totals == []


@pytest.mark.parametrize("field", ["messages", "line_items"])
@pytest.mark.parametrize(
    "value",
    [
        pytest.param(5),
        pytest.param(True),
        "abc",
        {"a": 1},
        [None, 5, "x", [1]],
    ],
)
def test_collections_of_the_wrong_type_do_not_crash(field: str, value: object) -> None:
    shops = reply({field: value})
    s = create(shops)
    if s.status == "created":
        assert getattr(s, {"line_items": "lines"}.get(field, field)) == []
    else:  # unreadable cart: it must be cancelled, not left behind
        assert shops.bodies[-1]["params"]["name"] == "cancel_cart"


@pytest.mark.parametrize(
    "value",
    [
        5,
        True,
        "abc",
        {"a": 1},
    ],
)
def test_line_item_totals_and_item_of_the_wrong_type_do_not_crash(
    value: object,
) -> None:
    shops = reply({"line_items": [{"quantity": 1, "item": value, "totals": value}]})
    s = create(shops)
    if s.status == "created":
        assert s.lines[0].amount is None and s.lines[0].title == ""
    else:
        assert shops.bodies[-1]["params"]["name"] == "cancel_cart"


def test_message_fields_that_are_not_strings() -> None:
    s = create(
        reply(
            {
                "messages": [
                    {"type": None, "code": 5, "content": {"a": 1}},
                    {"type": ["x"]},
                    {},
                ]
            }
        )
    )
    assert s.status == "created" and len(s.messages) == 3
    assert all(isinstance(m.content, str) for m in s.messages)


@pytest.mark.parametrize("amount", [5300.0, 53.5, "5300", None, [1]])
def test_non_integer_totals_are_dropped(amount: object) -> None:
    s = create(reply({"totals": [{"type": "total", "amount": amount}]}))
    assert s.totals == []


def test_boolean_total_is_dropped() -> None:
    s = create(reply({"totals": [{"type": "total", "amount": True}]}))
    assert s.totals == []


def test_boolean_line_amount_is_dropped() -> None:
    s = create(
        reply(
            {
                "line_items": [
                    {
                        "quantity": 1,
                        "item": {},
                        "totals": [{"type": "total", "amount": True}],
                    }
                ]
            }
        )
    )
    assert s.lines[0].amount is None


def test_negative_totals_are_kept_for_discounts() -> None:
    s = create(reply({"totals": [{"type": "discount", "amount": -500}]}))
    assert s.totals[0].amount == -500


@pytest.mark.parametrize("q", ["2", 2.0, None, [2], {}])
def test_non_integer_quantity_falls_back_to_one(q: object) -> None:
    s = create(reply({"line_items": [{"quantity": q, "item": {"title": "t"}}]}))
    assert s.lines[0].quantity == 1


def test_boolean_quantity_is_not_taken_literally() -> None:
    s = create(reply({"line_items": [{"quantity": False, "item": {"title": "t"}}]}))
    assert s.lines[0].quantity == 1


def test_currency_of_the_wrong_type_is_ignored() -> None:
    assert create(reply({"currency": 5})).currency is None


# ---------- continue_url ----------


@pytest.mark.parametrize(
    "url",
    [
        "https://",
        "https:///x",
        "https://[bad",
        "https://a b.com/x",
        "https://exa mple.com",
        "https://é.com/é",
        "https://a.com:99999/",
        "https://a.com/" + "x" * 100_000,
        "https://a.com/\n",
        "https://" + "\x00",
    ],
)
def test_odd_continue_urls_never_crash_a_session(url: str) -> None:
    s = create(reply({"continue_url": url}))
    assert s.status == "created"
    assert s.continue_url in (None, url)


@pytest.mark.parametrize(
    "url",
    [
        "https://",
        "https:///x",
        "https://a.com\n",
        "https://a.com/\r\nSet-Cookie: x",
        "https://\x00",
    ],
)
def test_https_only_drops_hostless_and_control_char_urls(url: str) -> None:
    assert https_only(url) is None


@pytest.mark.parametrize(
    "url",
    ["https://user:pw@shop-a.example.com/", "https://shop-a.example.com@evil.com/c"],
)
def test_continue_url_with_userinfo_is_dropped(url: str) -> None:
    assert https_only(url) is None


def test_continue_url_is_not_a_request_target() -> None:
    shops = reply({"continue_url": "https://127.0.0.1/steal"})
    create(shops)
    assert len(shops.requests) == 1


# ---------- redirects, failures, slow shops ----------


def test_redirects_are_not_followed() -> None:
    def h(r: httpx.Request, b: dict[str, Any]) -> httpx.Response:
        return httpx.Response(
            302, headers={"location": "https://127.0.0.1/api/ucp/mcp"}
        )

    shops = Shops(h)
    c = CartClient(
        "https://p.example/u.json",
        httpx.AsyncClient(transport=httpx.MockTransport(shops), follow_redirects=False),
    )
    s = asyncio.run(c.create(shop(), {V1: 1}))
    assert s.status == "error" and "302" in (s.error or "")
    assert [r.url.host for r in shops.requests] == ["shop-a.example.com"]
    assert not asyncio.run(c.cancel("shop-a.example.com", CART_ID))
    assert len(shops.requests) == 2


def test_default_client_does_not_follow_redirects() -> None:
    assert CartClient()._http.follow_redirects is False


@pytest.mark.parametrize("status", [201, 204, 301, 400, 401, 403, 404, 429, 500, 503])
def test_every_non_200_is_an_error_without_a_url_in_it(status: int) -> None:
    s = create(Shops(lambda r, b: httpx.Response(status, json=cart_reply())))
    assert (
        s.status == "error"
        and s.error is not None
        and "http" not in s.error.replace("HTTP", "")
    )


def test_a_hanging_shop_does_not_take_the_others_down() -> None:
    def h(r: httpx.Request, b: dict[str, Any]) -> httpx.Response:
        if r.url.host == "slow.example.com":
            raise httpx.ReadTimeout("t", request=r)
        if r.url.host == "dead.example.com":
            raise httpx.ConnectError("c", request=r)
        return httpx.Response(200, json=cart_reply())

    groups = {
        d: (shop(d), {V1: 1})
        for d in [
            "a.example.com",
            "slow.example.com",
            "b.example.com",
            "dead.example.com",
        ]
    }
    out = asyncio.run(create_carts(Shops(h).client(), groups))
    assert [s.status for s in out] == ["created", "error", "created", "error"]
    assert (
        out[1].error == "network error (ReadTimeout)"
        and out[3].error == "network error (ConnectError)"
    )


def test_a_truly_slow_shop_is_cut_off_by_the_client_timeout() -> None:
    async def slow(request: httpx.Request) -> httpx.Response:
        if request.url.host == "slow.example.com":
            await asyncio.sleep(5)
        return httpx.Response(200, json=cart_reply())

    async def go() -> list[Any]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(slow)) as http:
            c = CartClient("https://p.example/u.json", http)
            groups = {
                d: (shop(d), {V1: 1}) for d in ["a.example.com", "slow.example.com"]
            }
            return await asyncio.wait_for(create_carts(c, groups), timeout=1)

    # a hung shop with no timeout would block the whole request: this documents that it relies on TIMEOUT
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(go())


# ---------- grouping and size ----------


def test_one_hundred_line_items_for_one_shop() -> None:
    shops = Shops()
    create(shops, {f"gid://shopify/ProductVariant/{i}": 1 for i in range(100)})
    assert len(shops.bodies[0]["params"]["arguments"]["cart"]["line_items"]) == 100


def test_twenty_identical_products_make_quantity_20_and_more_is_refused(
    api: Callable[[Shops], TestClient],
) -> None:
    shops = Shops()
    c = api(shops)

    def layout(n: int) -> list[dict[str, Any]]:
        return [listing(f"p{i}", "shop-a.example.com", V1) for i in range(n)]

    c.post("/api/checkout", json={"layout": layout(20)})
    assert shops.bodies[0]["params"]["arguments"]["cart"]["line_items"] == [
        {"quantity": 20, "item": {"id": V1}}
    ]
    assert c.post("/api/checkout", json={"layout": layout(21)}).status_code == 422
    assert len(shops.requests) == 1


def test_ten_merchants_are_allowed_and_each_called_once(
    api: Callable[[Shops], TestClient],
) -> None:
    shops = Shops()
    layout = [listing(f"p{i}", f"s{i}.example.com") for i in range(10)] * 2
    res = api(shops).post("/api/checkout", json={"layout": layout})
    assert res.status_code == 200 and len(shops.requests) == 10


def test_duplicate_shop_with_different_case_and_ids_is_one_cart(
    api: Callable[[Shops], TestClient],
) -> None:
    shops = Shops()
    layout = [
        listing("a", "SHOP-A.example.com", V1, "gid://shopify/Shop/1"),
        listing("b", "shop-a.example.com", V1, "gid://shopify/Shop/2"),
    ]
    res = api(shops).post("/api/checkout", json={"layout": layout}).json()
    assert (
        len(res["sessions"]) == 1
        and res["sessions"][0]["shop"]["domain"] == "shop-a.example.com"
    )


def test_shop_with_an_empty_name_still_gets_a_cart(
    api: Callable[[Shops], TestClient],
) -> None:
    item = listing("a", "shop-a.example.com")
    item["product"]["shop"]["name"] = ""
    (s,) = (
        api(Shops()).post("/api/checkout", json={"layout": [item]}).json()["sessions"]
    )
    assert s["status"] == "created" and s["shop"]["name"] == ""


def test_missing_layout_is_422(api: Callable[[Shops], TestClient]) -> None:
    c = api(Shops())
    assert c.post("/api/checkout", json={}).status_code == 422
    assert c.post("/api/checkout", content="not json").status_code == 422
    assert (
        c.post("/api/checkout/cancel", json={"carts": [{"domain": "x"}]}).status_code
        == 422
    )


# ---------- cancel ----------


def test_cancel_idempotency_keys_are_unique_and_shaped_right() -> None:
    shops = Shops(
        lambda r, b: httpx.Response(200, json={"result": {"structuredContent": {}}})
    )
    c = shops.client()
    for _ in range(200):
        assert asyncio.run(c.cancel("shop-a.example.com", CART_ID))
    keys = [b["params"]["arguments"]["meta"]["idempotency-key"] for b in shops.bodies]
    assert len(set(keys)) == 200
    b = shops.bodies[0]["params"]
    assert b["name"] == "cancel_cart" and b["arguments"]["id"] == CART_ID


def test_cancel_endpoint_counts_and_limits(api: Callable[[Shops], TestClient]) -> None:
    def h(r: httpx.Request, b: dict[str, Any]) -> httpx.Response:
        return (
            httpx.Response(500)
            if r.url.host == "bad.example.com"
            else httpx.Response(200, json={"result": {"structuredContent": {}}})
        )

    c = api(Shops(h))
    carts = [
        {"domain": "Good.example.com ", "cart_id": CART_ID},
        {"domain": "bad.example.com", "cart_id": CART_ID},
        {"domain": "127.0.0.1", "cart_id": CART_ID},
    ]
    assert c.post("/api/checkout/cancel", json={"carts": carts}).json() == {
        "cancelled": 1,
        "failed": 2,
    }
    assert c.post("/api/checkout/cancel", json={"carts": []}).json() == {
        "cancelled": 0,
        "failed": 0,
    }
    many = [{"domain": f"s{i}.example.com", "cart_id": CART_ID} for i in range(11)]
    assert c.post("/api/checkout/cancel", json={"carts": many}).status_code == 422


def test_cancel_of_an_unknown_cart_as_error_reply_is_a_failure() -> None:
    s = Shops(lambda r, b: httpx.Response(200, json={"error": {"message": "gone"}}))
    assert not asyncio.run(s.client().cancel("shop-a.example.com", CART_ID))
