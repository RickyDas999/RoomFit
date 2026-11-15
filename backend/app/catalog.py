"""Shopify Global Catalog client (MCP over HTTP JSON-RPC).

Stateless by design (handoff section 6): nothing is written to disk. The only
thing kept is the OAuth token, in memory.
"""

import asyncio
import html
import os
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any, Literal

import httpx
from pydantic import BaseModel

from app.dimensions import Dimensions, Reason, parse_dimensions
from app.search import SEARCH_LIMIT

TOKEN_URL = "https://api.shopify.com/auth/access_token"
CATALOG_URL = "https://catalog.shopify.com/api/ucp/mcp"
PROFILE_URL = "https://raw.githubusercontent.com/RickyDas999/RoomFit/main/agent-profile/ucp-profile.json"
COUNTRY = "US"  # prototype: hard-coded (Ricky, Nov 15)
TOKEN_TTL = 55 * 60  # tokens last 60 min; refresh a bit early
MIN_INTERVAL = 0.2  # 5 requests/second limit
MAX_RETRIES = 3


MAX_RETRY_AFTER = 30.0


def _retry_after(value: str | None) -> float:
    """Seconds to wait. Falls back to 1s if missing or an HTTP-date; capped."""
    try:
        return min(max(float(value or "1"), 0.0), MAX_RETRY_AFTER)
    except ValueError:
        return 1.0


class CatalogError(Exception):
    """Raised for catalog failures. Never includes credentials or tokens."""


class Shop(BaseModel):
    id: str
    name: str
    domain: str


class Price(BaseModel):
    amount: int  # minor units
    currency: str


class Product(BaseModel):
    id: str
    variant_id: str
    title: str
    shop: Shop
    price: Price
    image_url: str | None
    url: str | None
    native_checkout: bool
    description: str  # plain text; M2's parser reads this
    dimensions: Dimensions | None = None  # W x D x H in inches, from the M2 parser
    dimension_source: str | None = None  # matched text snippet
    dimension_status: Literal["parsed", "ambiguous", "missing"] = "missing"
    dimension_reason: Reason | None = None  # why not "parsed"


def _plain(text: str) -> str:
    text = re.sub(r"(?is)<(script|style)\b.*?</\1\s*>", " ", text)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", text)).split())


def parse_product(raw: dict[str, Any]) -> Product | None:
    """Parse one catalog product. Returns None if it is unusable (never raises)."""
    try:
        v = next(
            (
                v
                for v in raw.get("variants") or []
                if v.get("price") and v.get("seller")
            ),
            None,
        )
        if v is None:
            return None
        price, seller = v["price"], v["seller"]
        media = raw.get("media") or []
        desc = (raw.get("description") or {}).get("html") or (
            v.get("description") or {}
        ).get("plain", "")
        text = _plain(desc)
        dims = parse_dimensions(text)
        return Product(
            id=raw["id"],
            variant_id=v["id"],
            title=raw.get("title", ""),
            shop=Shop(
                id=seller["id"],
                name=seller.get("name", ""),
                domain=seller.get("domain", ""),
            ),
            price=Price(amount=price["amount"], currency=price["currency"]),
            image_url=media[0].get("url") if media else None,
            url=raw.get("url"),
            native_checkout=bool((v.get("eligible") or {}).get("native_checkout")),
            description=text,
            dimensions=dims.dimensions,
            dimension_source=dims.source,
            dimension_status=dims.status,
            dimension_reason=dims.reason,
        )
    except (
        KeyError,
        TypeError,
        ValueError,
        AttributeError,
    ):  # ValueError covers pydantic
        return None


class CatalogClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        http: httpx.AsyncClient | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._id, self._secret = client_id, client_secret
        self._http = http or httpx.AsyncClient(timeout=30)
        self._sleep, self._now = sleep, now
        self._token: str | None = None
        self._token_expires = 0.0
        self._next_call = 0.0
        self._lock = asyncio.Lock()
        self._token_lock = asyncio.Lock()
        self._rpc_id = 0

    @classmethod
    def from_env(cls) -> "CatalogClient":
        try:
            return cls(
                os.environ["SHOPIFY_CLIENT_ID"], os.environ["SHOPIFY_CLIENT_SECRET"]
            )
        except KeyError as e:
            raise CatalogError(
                f"missing env var {e.args[0]} (see backend/.env.example)"
            ) from None

    async def _get_token(self) -> str:
        async with self._token_lock:  # concurrent searches share one token fetch
            if self._token and self._now() < self._token_expires:
                return self._token
            r = await self._http.post(
                TOKEN_URL,
                json={
                    "client_id": self._id,
                    "client_secret": self._secret,
                    "grant_type": "client_credentials",
                },
            )
            if r.status_code != 200:
                raise CatalogError(f"token request failed: HTTP {r.status_code}")
            try:
                self._token = str(r.json()["access_token"])
            except (ValueError, KeyError, TypeError):
                raise CatalogError("token response had no access_token") from None
            self._token_expires = self._now() + TOKEN_TTL
            return self._token

    async def _throttle(self) -> None:
        # ponytail: one lock spaces all calls 0.2s apart; fine for ~5 slots per request
        async with self._lock:
            wait = self._next_call - self._now()
            if wait > 0:
                await self._sleep(wait)
            self._next_call = self._now() + MIN_INTERVAL

    async def search(self, query: str, limit: int = SEARCH_LIMIT) -> list[Product]:
        self._rpc_id += 1
        body = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": self._rpc_id,
            "params": {
                "name": "search_catalog",
                "arguments": {
                    "meta": {"ucp-agent": {"profile": PROFILE_URL}},
                    "catalog": {
                        "query": query,
                        "filters": {
                            "ships_to": {"country": COUNTRY},
                            "available": True,
                        },
                        "context": {"address_country": COUNTRY},
                        "pagination": {"limit": limit},
                    },
                },
            },
        }
        for attempt in range(MAX_RETRIES + 1):
            await self._throttle()
            token = await self._get_token()
            r = await self._http.post(
                CATALOG_URL, json=body, headers={"Authorization": f"Bearer {token}"}
            )
            if r.status_code != 429:
                break
            if attempt == MAX_RETRIES:
                raise CatalogError("rate limited (HTTP 429) after retries")
            await self._sleep(_retry_after(r.headers.get("Retry-After")))
        if r.status_code != 200:
            raise CatalogError(f"search failed: HTTP {r.status_code}")
        try:
            data = r.json()
        except ValueError:
            raise CatalogError("search response was not JSON") from None
        if not isinstance(data, dict):
            raise CatalogError("search response was not a JSON object")
        if data.get("error"):
            message = (data["error"] or {}).get("message", "unknown")
            raise CatalogError(f"search error: {message}")
        result = data.get("result") or {}
        if result.get("isError"):
            raise CatalogError("search error: tool reported isError")
        raw = (result.get("structuredContent") or {}).get("products") or []
        return [p for p in map(parse_product, raw) if p]
