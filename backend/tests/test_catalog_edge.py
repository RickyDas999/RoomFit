"""Edge cases the main catalog tests miss. Mocked httpx only, synthetic data."""

import asyncio
import itertools
from typing import Any

import httpx
import pytest
from test_catalog import Clock, make_product

from app.catalog import (
    CATALOG_URL,
    TOKEN_URL,
    CatalogClient,
    CatalogError,
    parse_product,
)


def client_for(
    search: Any, clock: Clock | None = None, tokens: list[int] | None = None
) -> tuple[CatalogClient, Clock, dict[str, int]]:
    """search(n) -> httpx.Response for the n-th catalog call (0-based)."""
    clock = clock or Clock()
    counts = {"token": 0, "search": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URL:
            counts["token"] += 1
            return httpx.Response(200, json={"access_token": f"tok-{counts['token']}"})
        assert str(request.url) == CATALOG_URL
        n = counts["search"]
        counts["search"] += 1
        return search(n, request)  # type: ignore[no-any-return]

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return (
        CatalogClient("cid", "sec", http=http, sleep=clock.sleep, now=clock.now),
        clock,
        counts,
    )


def ok(products: list[dict[str, Any]]) -> httpx.Response:
    return httpx.Response(
        200, json={"result": {"structuredContent": {"products": products}}}
    )


# --- Retry-After handling -------------------------------------------------


@pytest.mark.parametrize("value", [None, "soon", "Wed, 21 Oct 2026 07:28:00 GMT", ""])
def test_429_with_missing_or_unparseable_retry_after_still_retries(
    value: str | None,
) -> None:
    headers = {} if value is None else {"Retry-After": value}
    client, clock, counts = client_for(
        lambda n, r: (
            httpx.Response(429, headers=headers) if n == 0 else ok([make_product()])
        )
    )
    assert len(asyncio.run(client.search("x"))) == 1
    assert counts["search"] == 2
    assert all(s >= 0 for s in clock.sleeps)


def test_429_negative_retry_after_does_not_crash() -> None:
    client, _, counts = client_for(
        lambda n, r: (
            httpx.Response(429, headers={"Retry-After": "-5"}) if n == 0 else ok([])
        )
    )
    assert asyncio.run(client.search("x")) == []
    assert counts["search"] == 2


def test_429_huge_retry_after_is_capped() -> None:
    client, clock, _ = client_for(
        lambda n, r: (
            httpx.Response(429, headers={"Retry-After": "86400"}) if n == 0 else ok([])
        )
    )
    asyncio.run(client.search("x"))
    assert max(clock.sleeps) <= 60  # a request must not hang for a day


# --- token lifecycle ------------------------------------------------------


def test_token_expiring_during_429_wait_is_refreshed_for_retry() -> None:
    seen: list[str] = []

    def search(n: int, r: httpx.Request) -> httpx.Response:
        seen.append(r.headers["Authorization"])
        if n == 0:
            return httpx.Response(429, headers={"Retry-After": "3600"})
        return ok([])

    client, clock, counts = client_for(search)
    # cap may shorten the wait, so also push the clock past TTL via the 429 sleep
    orig = clock.sleep

    async def long_sleep(s: float) -> None:
        await orig(max(s, 56 * 60))

    client._sleep = long_sleep
    asyncio.run(client.search("x"))
    assert counts["token"] == 2
    assert seen == ["Bearer tok-1", "Bearer tok-2"]


def test_concurrent_searches_share_one_token() -> None:
    client, _, counts = client_for(lambda n, r: ok([]))

    async def go() -> None:
        await asyncio.gather(*(client.search(f"q{i}") for i in range(5)))

    asyncio.run(go())
    assert counts["token"] == 1


def test_token_response_without_access_token_raises_catalog_error() -> None:
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"error": "nope"})
        )
    )
    with pytest.raises(CatalogError):
        asyncio.run(CatalogClient("c", "s", http=http).search("x"))


# --- response shapes ------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"result": {}},
        {"result": {"structuredContent": {}}},
        {"result": {"structuredContent": {"products": []}}},
    ],
)
def test_missing_or_empty_products_returns_empty_list(body: dict[str, Any]) -> None:
    client, _, _ = client_for(lambda n, r: httpx.Response(200, json=body))
    assert asyncio.run(client.search("x")) == []


@pytest.mark.parametrize(
    "body",
    [
        {"result": None},
        {"result": {"structuredContent": None}},
        {"result": {"structuredContent": {"products": None}}},
    ],
)
def test_null_fields_in_response_do_not_crash(body: dict[str, Any]) -> None:
    client, _, _ = client_for(lambda n, r: httpx.Response(200, json=body))
    assert asyncio.run(client.search("x")) == []


@pytest.mark.parametrize(
    "content", [b"<html>502 bad gateway</html>", b"", b"{not json"]
)
def test_malformed_json_body_raises_catalog_error(content: bytes) -> None:
    client, _, _ = client_for(lambda n, r: httpx.Response(200, content=content))
    with pytest.raises(CatalogError):
        asyncio.run(client.search("x"))


def test_non_object_json_body_raises_catalog_error() -> None:
    client, _, _ = client_for(lambda n, r: httpx.Response(200, json=[1, 2]))
    with pytest.raises(CatalogError):
        asyncio.run(client.search("x"))


def test_one_malformed_product_does_not_sink_the_rest() -> None:
    bad = make_product(2)
    bad["variants"][0]["price"] = {"amount": "12.50", "currency": "USD"}
    no_id = make_product(3)
    del no_id["id"]
    client, _, _ = client_for(lambda n, r: ok([bad, no_id, make_product(1)]))
    products = asyncio.run(client.search("x"))
    assert [p.id for p in products] == ["gid://shopify/p/1"]


# --- parse_product --------------------------------------------------------


def test_price_amount_as_numeric_string() -> None:
    raw = make_product()
    raw["variants"][0]["price"]["amount"] = "8999"
    p = parse_product(raw)
    assert p is not None and p.price.amount == 8999


def test_price_amount_decimal_string_is_skipped_not_raised() -> None:
    raw = make_product()
    raw["variants"][0]["price"]["amount"] = "89.99"
    assert parse_product(raw) is None


def test_unusable_first_variant_falls_back_to_next() -> None:
    raw = make_product()
    second = {**raw["variants"][0], "id": "gid://shopify/ProductVariant/2"}
    del raw["variants"][0]["price"]  # variants[0] unavailable
    raw["variants"].append(second)
    p = parse_product(raw)
    assert p is not None and p.variant_id == "gid://shopify/ProductVariant/2"


def test_script_tags_stripped_from_description() -> None:
    raw = make_product(
        description={"html": "<p>Desk</p><script>alert(1)</script><b>40in</b>"}
    )
    p = parse_product(raw)
    assert p is not None
    assert "<" not in p.description and "alert" not in p.description
    assert "40in" in p.description


def test_entities_decoded_and_whitespace_collapsed() -> None:
    raw = make_product(
        description={"html": "A&amp;B&nbsp;&nbsp;&#8243;\n\n<br/>\t30&times;15"}
    )
    p = parse_product(raw)
    assert p is not None
    assert "  " not in p.description and "&amp;" not in p.description
    assert p.description.startswith("A&B")


def test_unclosed_tag_does_not_swallow_description() -> None:
    raw = make_product(description={"html": "Desk 40 in wide <b unclosed"})
    p = parse_product(raw)
    assert p is not None and p.description.startswith("Desk 40 in wide")


def test_huge_description_parses_quickly() -> None:
    import time

    big = "<p>" + ("word &amp; <b>x</b> " * 100_000) + "</p>"
    t = time.perf_counter()
    p = parse_product(make_product(description={"html": big}))
    assert p is not None and p.description.startswith("word & x")
    assert time.perf_counter() - t < 2


# --- concurrency / rate spacing ------------------------------------------


def test_concurrent_searches_respect_spacing_and_get_own_results() -> None:
    clock = Clock()
    stamps: list[float] = []

    def search(n: int, r: httpx.Request) -> httpx.Response:
        stamps.append(clock.t)
        return ok([make_product(n)])

    client, _, counts = client_for(search, clock)

    async def go() -> list[list[Any]]:
        return list(await asyncio.gather(*(client.search(f"q{i}") for i in range(5))))

    results = asyncio.run(go())
    assert counts["search"] == 5 and all(len(r) == 1 for r in results)
    gaps = [b - a for a, b in itertools.pairwise(stamps)]
    assert all(g >= 0.2 - 1e-9 for g in gaps), gaps


def test_rpc_ids_unique_across_concurrent_searches() -> None:
    import json

    ids: list[int] = []

    def search(n: int, r: httpx.Request) -> httpx.Response:
        ids.append(json.loads(r.content)["id"])
        return ok([])

    client, _, _ = client_for(search)

    async def go() -> None:
        await asyncio.gather(*(client.search("x") for _ in range(4)))

    asyncio.run(go())
    assert len(set(ids)) == 4
