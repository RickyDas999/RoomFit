"""UCP carts per merchant: the "checkout" step of the prototype. No purchase, ever.

Shopify's catalog marks every product `native_checkout: false`, so a UCP checkout session is not
offered for any of them. A UCP cart works for any Shopify product and needs no token and no buyer
IP (the documented fallback). The app makes one cart per merchant, shows what the merchant
returned, and hands the buyer to the merchant's own site (`continue_url`). Carts are cancelled
when the room changes, when the page closes, or on request.

Rules: never log `continue_url`; only pass it on if it is https; never hold payment details.
"""

import asyncio
import os
import re
import uuid
from typing import Any, Literal

import httpx
from pydantic import BaseModel

from app.catalog import PROFILE_URL, Shop

TIMEOUT = 20.0
MAX_SHOPS = 10
_HOST = re.compile(r"^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
_VARIANT = re.compile(r"^gid://shopify/ProductVariant/\d{1,20}$")
_CART = re.compile(r"^gid://shopify/Cart/[A-Za-z0-9_?=&.-]{1,200}$")
_BLOCKED_SUFFIXES = (".local", ".internal", ".localhost", ".lan", ".home", ".corp")


def valid_shop_domain(domain: str) -> bool:
    """A plain public-looking hostname: no scheme, port, path or IP. The browser supplies it, and the
    server calls it, so it must not be able to point the server at an internal address."""
    d = domain.strip()
    return bool(_HOST.match(d)) and d == d.lower() and not d.endswith(_BLOCKED_SUFFIXES)


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
    if not isinstance(url, str) or not url.startswith("https://"):
        return None
    return url if httpx.URL(url).host else None


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
        r = await self._http.post(f"https://{domain}/api/ucp/mcp", json=_rpc(name, arguments))
        if r.status_code == 429:
            raise CartCallError("the shop is rate limiting us (HTTP 429)")
        if r.status_code != 200:
            raise CartCallError(f"the shop answered HTTP {r.status_code}")
        try:
            data = r.json()
        except ValueError:
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

    async def create(self, shop: Shop, variants: dict[str, int]) -> CartSession:
        """One cart at one shop. `variants` maps variant id to quantity. Never raises."""
        if not valid_shop_domain(shop.domain):
            return CartSession(shop=shop, status="error", error="not a usable shop address")
        if not variants or not all(_VARIANT.match(v) for v in variants):
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
        messages = [
            Message(
                type=str(m.get("type", "info")),
                code=str(m.get("code", "")),
                content=str(m.get("content", ""))[:300],
            )
            for m in cart.get("messages") or []
            if isinstance(m, dict)
        ]
        cart_id = cart.get("id")
        if not isinstance(cart_id, str) or not _CART.match(cart_id):
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

    async def cancel(self, domain: str, cart_id: str) -> bool:
        """Cancel one cart. True if the shop confirmed (or no longer knows the cart)."""
        if not valid_shop_domain(domain) or not _CART.match(cart_id):
            return False
        args = {"meta": self._meta(**{"idempotency-key": str(uuid.uuid4())}), "id": cart_id}
        try:
            await self._call(domain, "cancel_cart", args)
        except (CartCallError, httpx.HTTPError):
            return False
        return True


def _lines(cart: dict[str, Any]) -> list[CartLine]:
    out: list[CartLine] = []
    for li in cart.get("line_items") or []:
        if not isinstance(li, dict):
            continue
        raw_item = li.get("item")
        item: dict[str, Any] = raw_item if isinstance(raw_item, dict) else {}
        total = next(
            (t.get("amount") for t in li.get("totals") or [] if isinstance(t, dict) and t.get("type") == "total"),
            None,
        )
        qty = li.get("quantity")
        out.append(
            CartLine(
                title=str(item.get("title", ""))[:200],
                quantity=qty if isinstance(qty, int) else 1,
                amount=total if isinstance(total, int) else None,
            )
        )
    return out


def _totals(raw: object) -> list[Total]:
    out: list[Total] = []
    for t in raw if isinstance(raw, list) else []:
        if isinstance(t, dict) and isinstance(t.get("amount"), int) and isinstance(t.get("type"), str):
            out.append(Total(type=t["type"], amount=t["amount"], display_text=str(t.get("display_text", ""))[:40]))
    return out


async def create_carts(client: CartClient, groups: dict[str, tuple[Shop, dict[str, int]]]) -> list[CartSession]:
    """One cart per merchant, in parallel (grouped by shop domain, in the order first seen)."""
    return list(await asyncio.gather(*(client.create(shop, v) for shop, v in groups.values())))
