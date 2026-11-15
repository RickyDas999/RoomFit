import asyncio
import builtins
import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

import app.catalog as catalog_module
from app.catalog import (
    CATALOG_URL,
    PROFILE_URL,
    TOKEN_URL,
    CatalogClient,
    CatalogError,
    parse_product,
)

SECRET = "s3cret-value"


def make_product(n: int = 1, **over: Any) -> dict[str, Any]:
    """Synthetic listing shaped like a real response (made up, not Shopify data)."""
    p: dict[str, Any] = {
        "id": f"gid://shopify/p/{n}",
        "title": f"Test Desk {n}",
        "url": f"https://shop.example/products/{n}",
        "description": {"html": "<p>Desk 40&quot;W x 20&quot;D</p><br>Sturdy"},
        "media": [{"type": "image", "url": "https://img.example/1.jpg"}],
        "variants": [
            {
                "id": f"gid://shopify/ProductVariant/{n}",
                "price": {"amount": 8999, "currency": "USD"},
                "eligible": {"native_checkout": True},
                "seller": {"id": "gid://shopify/Shop/9", "name": "Test Shop", "domain": "shop.example"},
            }
        ],
    }
    p.update(over)
    return p


class Fake:
    """Mock Shopify: records requests, serves token + search from a script of search statuses."""

    def __init__(self, statuses: list[int] | None = None, products: list[dict[str, Any]] | None = None):
        self.requests: list[httpx.Request] = []
        self.statuses = statuses or [200]
        self.products = [make_product()] if products is None else products
        self.token_calls = 0
        self.searches = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if str(request.url) == TOKEN_URL:
            self.token_calls += 1
            return httpx.Response(200, json={"access_token": "tok-abc"})
        assert str(request.url) == CATALOG_URL
        status = self.statuses[min(self.searches, len(self.statuses) - 1)]
        self.searches += 1
        if status == 429:
            return httpx.Response(429, headers={"Retry-After": "7"}, json={"error": {"code": -32000}})
        return httpx.Response(
            status,
            json={"jsonrpc": "2.0", "id": 1, "result": {"structuredContent": {"products": self.products}}},
        )


class Clock:
    def __init__(self) -> None:
        self.t = 0.0
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self.t

    async def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.t += s


def make_client(fake: Fake, clock: Clock | None = None) -> CatalogClient:
    clock = clock or Clock()
    http = httpx.AsyncClient(transport=httpx.MockTransport(fake))
    return CatalogClient("cid", SECRET, http=http, sleep=clock.sleep, now=clock.now)


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_request_shape() -> None:
    fake = Fake()
    run(make_client(fake).search("desk 40 inch", limit=30))
    token_req, search_req = fake.requests
    assert json.loads(token_req.content) == {
        "client_id": "cid", "client_secret": SECRET, "grant_type": "client_credentials",
    }
    assert search_req.headers["Authorization"] == "Bearer tok-abc"
    body = json.loads(search_req.content)
    assert body["method"] == "tools/call"
    assert body["params"]["name"] == "search_catalog"
    args = body["params"]["arguments"]
    assert args["meta"]["ucp-agent"]["profile"] == PROFILE_URL
    cat = args["catalog"]
    assert cat["query"] == "desk 40 inch"
    assert cat["filters"] == {"ships_to": {"country": "US"}, "available": True}
    assert cat["context"] == {"address_country": "US"}
    assert cat["pagination"] == {"limit": 30}


def test_parses_product() -> None:
    [p] = run(make_client(Fake()).search("x"))
    assert p.id == "gid://shopify/p/1"
    assert p.variant_id == "gid://shopify/ProductVariant/1"
    assert (p.shop.name, p.shop.domain) == ("Test Shop", "shop.example")
    assert (p.price.amount, p.price.currency) == (8999, "USD")
    assert p.native_checkout is True
    assert p.image_url == "https://img.example/1.jpg"
    assert p.description == 'Desk 40"W x 20"D Sturdy'
    assert p.dimensions is None and p.dimension_source is None


def test_parse_skips_unusable_products() -> None:
    assert parse_product(make_product(variants=[])) is None
    assert parse_product({"id": "gid://shopify/p/1"}) is None
    no_seller = make_product()
    del no_seller["variants"][0]["seller"]
    assert parse_product(no_seller) is None


def test_parse_handles_missing_optional_fields() -> None:
    raw = make_product(media=[], description=None, url=None)
    raw["variants"][0]["eligible"] = {}
    p = parse_product(raw)
    assert p is not None
    assert (p.image_url, p.url, p.description, p.native_checkout) == (None, None, "", False)


def test_variant_plain_description_fallback() -> None:
    raw = make_product(description=None)
    raw["variants"][0]["description"] = {"plain": "Plain text 30 in"}
    p = parse_product(raw)
    assert p is not None and p.description == "Plain text 30 in"


def test_token_reused_then_refreshed_after_expiry() -> None:
    fake, clock = Fake(), Clock()
    client = make_client(fake, clock)
    run(client.search("a"))
    run(client.search("b"))
    assert fake.token_calls == 1
    clock.t += 56 * 60
    run(client.search("c"))
    assert fake.token_calls == 2


def test_429_waits_retry_after_then_succeeds() -> None:
    fake, clock = Fake(statuses=[429, 200]), Clock()
    products = run(make_client(fake, clock).search("x"))
    assert len(products) == 1
    assert fake.searches == 2
    assert 7.0 in clock.sleeps


def test_repeated_429_raises() -> None:
    fake = Fake(statuses=[429])
    with pytest.raises(CatalogError, match="429"):
        run(make_client(fake).search("x"))
    assert fake.searches == 4  # first try + 3 retries


def test_server_error_raises_without_secrets() -> None:
    with pytest.raises(CatalogError) as e:
        run(make_client(Fake(statuses=[500])).search("x"))
    assert "500" in str(e.value) and SECRET not in str(e.value) and "tok-abc" not in str(e.value)


def test_jsonrpc_error_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URL:
            return httpx.Response(200, json={"access_token": "t"})
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "error": {"message": "bad"}})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(CatalogError, match="bad"):
        run(CatalogClient("c", "s", http=http).search("x"))


def test_token_failure_raises() -> None:
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(401)))
    with pytest.raises(CatalogError, match="token"):
        run(CatalogClient("c", "s", http=http).search("x"))


def test_calls_are_spaced_for_rate_limit() -> None:
    fake, clock = Fake(), Clock()
    client = make_client(fake, clock)
    run(client.search("a"))
    t_first = clock.t
    run(client.search("b"))
    assert clock.t - t_first >= 0.2 - 1e-9


def test_missing_env_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SHOPIFY_CLIENT_ID", raising=False)
    with pytest.raises(CatalogError, match="SHOPIFY_CLIENT_ID"):
        CatalogClient.from_env()


def test_secrets_not_logged(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    run(make_client(Fake()).search("x"))
    assert SECRET not in caplog.text and "tok-abc" not in caplog.text


def test_writes_no_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    real_open: Callable[..., Any] = builtins.open

    def guarded(file: Any, mode: str = "r", *a: Any, **k: Any) -> Any:
        if any(c in mode for c in "wax+"):
            raise AssertionError(f"write attempted: {file}")
        return real_open(file, mode, *a, **k)

    monkeypatch.setattr(builtins, "open", guarded)
    run(make_client(Fake(statuses=[429, 200])).search("x"))
    assert list(tmp_path.iterdir()) == []


def test_catalog_source_has_no_persistence() -> None:
    src = Path(catalog_module.__file__).read_text()
    for banned in ("open(", "write_text", "write_bytes", "sqlite", "shelve", "pickle"):
        assert banned not in src
