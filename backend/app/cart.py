"""UCP carts per merchant: the "checkout" step of the prototype. No purchase, ever.

Shopify's catalog marks every product `native_checkout: false`, so a UCP checkout session is not
offered for any of them. A UCP cart works for any Shopify product and needs no token and no buyer
IP (the documented fallback). The app makes one cart per merchant, shows what the merchant
returned, and hands the buyer to the merchant's own site (`continue_url`). Carts are cancelled
when the room changes, when the page closes, or on request.

Rules: never log `continue_url`; only pass it on if it is https; never hold payment details.
"""

import asyncio
import json
import os
import re
import uuid
from typing import Any, Literal

import httpx
from pydantic import BaseModel

from app.catalog import PROFILE_URL, Shop

TIMEOUT = 20.0  # per read
TOTAL_TIMEOUT = 25.0  # per call, however slowly a shop drips its answer
MAX_BODY = 1_000_000  # bytes of a shop's answer we are willing to read
MAX_SHOPS = 10
_HOST = re.compile(r"^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
_VARIANT = re.compile(r"^gid://shopify/ProductVariant/\d{1,20}$")
_CART = re.compile(r"^gid://shopify/Cart/[A-Za-z0-9_?=&.-]{1,200}$")
_BLOCKED_SUFFIXES = (
    ".local", ".internal", ".localhost", ".localdomain", ".lan", ".home", ".corp",
    ".intranet", ".private", ".arpa",
)


def valid_shop_domain(domain: str) -> bool:
    """A plain public-looking hostname: no scheme, port, path or IP. The browser supplies it, and the
    server calls it, so it must not be able to point the server at an internal address."""
    return (
        bool(_HOST.fullmatch(domain))
        and domain == domain.lower()
        and not domain.endswith(_BLOCKED_SUFFIXES)
    )


class CartLine(BaseModel):
    title: str
    quantity: int
    amount: int | None = None  # minor units (cents)


class Total(BaseModel):
    type: str
    amount: int
    display_text: str = ""


class Message(BaseModel):
    type: str = "info"
    code: str = ""
    content: str = ""


class CartSession(BaseModel):
    shop: Shop
    status: Literal["created", "error"]
    cart_id: str | None = None
    currency: str | None = None
    lines: list[CartLine] = []
    totals: list[Total] = []
    messages: list[Message] = []
    continue_url: str | None = None  # https only; never logged
    error: str | None = None


class CartCallError(Exception):
    """A shop call failed. The message is safe to show (no URLs, tokens or ids)."""


def https_only(url: object) -> str | None:
    """The link if it is a plain https URL (no spaces, no user:password@), else None."""
    if not isinstance(url, str) or len(url) > 2000 or not url.startswith("https://"):
        return None
    if any(c.isspace() or ord(c) < 32 or ord(c) > 126 for c in url):
        return None
    try:
        parsed = httpx.URL(url)
    except httpx.InvalidURL:
        return None
    return url if parsed.host and not parsed.userinfo else None


def _rpc(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "id": 1,
        "params": {"name": name, "arguments": arguments},
    }


class CartClient:
    def __init__(self, profile_url: str = PROFILE_URL, http: httpx.AsyncClient | None = None) -> None:
        self._profile = profile_url
        self._http = http or httpx.AsyncClient(timeout=TIMEOUT)

    @classmethod
    def from_env(cls) -> "CartClient":
        # UCP_PROFILE_URL: test a profile that is not on main yet (optional)
        return cls(os.environ.get("UCP_PROFILE_URL") or PROFILE_URL)

    def _meta(self, **extra: str) -> dict[str, Any]:
        return {"ucp-agent": {"profile": self._profile}, **extra}

    async def _call(self, domain: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            async with asyncio.timeout(TOTAL_TIMEOUT):
                status, raw = await self._post(f"https://{domain}/api/ucp/mcp", _rpc(name, arguments))
        except TimeoutError:
            raise CartCallError("the shop took too long to answer") from None
        if status == 429:
            raise CartCallError("the shop is rate limiting us (HTTP 429)")
        if status != 200:
            raise CartCallError(f"the shop answered HTTP {status}")
        try:
            data = json.loads(raw)
        except (ValueError, RecursionError):
            raise CartCallError("the shop's answer was not JSON") from None
        if not isinstance(data, dict):
            raise CartCallError("the shop's answer was not a JSON object")
        if data.get("error"):
            err = data["error"] if isinstance(data["error"], dict) else {}
            raise CartCallError(f"the shop refused: {str(err.get('message', 'error'))[:120]}")
        result = data.get("result")
        sc = result.get("structuredContent") if isinstance(result, dict) else None
        if not isinstance(sc, dict):
            raise CartCallError("the shop's answer had no cart")
        return sc

    async def _post(self, url: str, body: dict[str, Any]) -> tuple[int, bytes]:
        """POST and read at most MAX_BODY bytes. Redirects are not followed."""
        async with self._http.stream("POST", url, json=body) as r:
            chunks: list[bytes] = []
            size = 0
            async for chunk in r.aiter_bytes():
                size += len(chunk)
                if size > MAX_BODY:
                    raise CartCallError("the shop's answer was too large")
                chunks.append(chunk)
            return r.status_code, b"".join(chunks)

    async def create(self, shop: Shop, variants: dict[str, int]) -> CartSession:
        """One cart at one shop. `variants` maps variant id to quantity. Never raises."""
        if not valid_shop_domain(shop.domain):
            return CartSession(shop=shop, status="error", error="not a usable shop address")
        if not variants or not all(_VARIANT.fullmatch(v) for v in variants):
            return CartSession(shop=shop, status="error", error="not a usable product id")
        args = {
            "meta": self._meta(),
            "cart": {
                "line_items": [
                    {"quantity": q, "item": {"id": v}} for v, q in variants.items()
                ],
                "context": {"address_country": "US"},
            },
        }
        try:
            sc = await self._call(shop.domain, "create_cart", args)
        except (CartCallError, httpx.HTTPError) as e:
            msg = str(e) if isinstance(e, CartCallError) else f"network error ({type(e).__name__})"
            return CartSession(shop=shop, status="error", error=msg)
        raw_cart = sc.get("cart")
        cart: dict[str, Any] = raw_cart if isinstance(raw_cart, dict) else sc
        cart_id = cart.get("id")
        try:
            messages = _messages(cart.get("messages"))
            if not isinstance(cart_id, str) or not _CART.fullmatch(cart_id):
                why = next((m.content for m in messages if m.type == "error"), "the shop made no cart")
                return CartSession(shop=shop, status="error", messages=messages, error=why)
            return CartSession(
                shop=shop,
                status="created",
                cart_id=cart_id,
                currency=cart.get("currency") if isinstance(cart.get("currency"), str) else None,
                lines=_lines(cart),
                totals=_totals(cart.get("totals")),
                messages=messages,
                continue_url=https_only(cart.get("continue_url")),
            )
        except (TypeError, ValueError, AttributeError, KeyError, RecursionError):
            # a cart exists but we cannot read it: do not leave it behind
            if isinstance(cart_id, str):
                await self.cancel(shop.domain, cart_id)
            return CartSession(shop=shop, status="error", error="the shop's cart could not be read")

    async def cancel(self, domain: str, cart_id: str) -> bool:
        """Cancel one cart. True if the shop answered and the cart is gone (a "not found" answer
        counts: it is already gone). False for an unusable address or id, or a failed call."""
        if not valid_shop_domain(domain) or not _CART.fullmatch(cart_id):
            return False
        args = {"meta": self._meta(**{"idempotency-key": str(uuid.uuid4())}), "id": cart_id}
        try:
            sc = await self._call(domain, "cancel_cart", args)
        except (CartCallError, httpx.HTTPError):
            return False
        raw = sc.get("cart")
        cart: dict[str, Any] = raw if isinstance(raw, dict) else sc
        bad = {m.code for m in _messages_safe(cart.get("messages")) if m.type == "error"}
        return not (bad - {"cart_not_found"})


def _messages_safe(raw: object) -> list[Message]:
    try:
        return _messages(raw)
    except (TypeError, ValueError, AttributeError):
        return []


def _messages(raw: object) -> list[Message]:
    return [
        Message(
            type=str(m.get("type", "info")),
            code=str(m.get("code", "")),
            content=str(m.get("content", ""))[:300],
        )
        for m in (raw if isinstance(raw, list) else [])
        if isinstance(m, dict)
    ]


def _int(x: object) -> int | None:
    """An int, but not a bool (True is an int in Python)."""
    return x if isinstance(x, int) and not isinstance(x, bool) else None


def _lines(cart: dict[str, Any]) -> list[CartLine]:
    out: list[CartLine] = []
    raw_lines = cart.get("line_items")
    for li in raw_lines if isinstance(raw_lines, list) else []:
        if not isinstance(li, dict):
            continue
        raw_item = li.get("item")
        item: dict[str, Any] = raw_item if isinstance(raw_item, dict) else {}
        li_totals = li.get("totals")
        total = next(
            (
                t.get("amount")
                for t in (li_totals if isinstance(li_totals, list) else [])
                if isinstance(t, dict) and t.get("type") == "total"
            ),
            None,
        )
        qty = li.get("quantity")
        out.append(
            CartLine(
                title=str(item.get("title", ""))[:200],
                quantity=q if (q := _int(qty)) is not None and q > 0 else 1,
                amount=_int(total),
            )
        )
    return out


def _totals(raw: object) -> list[Total]:
    out: list[Total] = []
    for t in raw if isinstance(raw, list) else []:
        if isinstance(t, dict) and _int(t.get("amount")) is not None and isinstance(t.get("type"), str):
            out.append(Total(type=t["type"], amount=t["amount"], display_text=str(t.get("display_text", ""))[:40]))
    return out


async def create_carts(client: CartClient, groups: dict[str, tuple[Shop, dict[str, int]]]) -> list[CartSession]:
    """One cart per merchant, in parallel (grouped by shop domain, in the order first seen)."""
    shops = list(groups.values())
    done = await asyncio.gather(*(client.create(shop, v) for shop, v in shops), return_exceptions=True)
    return [
        d if isinstance(d, CartSession) else CartSession(shop=shop, status="error", error="the cart could not be made")
        for d, (shop, _) in zip(done, shops, strict=True)
    ]
