"""Dev only: print live catalog results per role. Writes nothing to disk.

Run from backend/:  python -m scripts.dev_catalog
Needs SHOPIFY_CLIENT_ID / SHOPIFY_CLIENT_SECRET in backend/.env (or the environment).
"""

import asyncio
import os
from pathlib import Path

from app.catalog import CatalogClient
from app.search import Role, build_query

# Sample room until M3 (room.py): 144 x 192 in. Footprints are rough placeholders.
FOOTPRINTS: dict[Role, tuple[float, float]] = {
    "bed": (40, 80),
    "desk": (48, 24),
    "desk_chair": (24, 24),
    "dresser": (36, 18),
    "nightstand": (18, 16),
}


def load_env() -> None:
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            key, sep, value = line.partition("=")
            if sep and not line.startswith("#"):
                os.environ.setdefault(key.strip(), value.strip())


async def main() -> None:
    load_env()
    client = CatalogClient.from_env()
    for role, footprint in FOOTPRINTS.items():
        query = build_query(role, footprint)
        print(f"\n== {role}: {query!r}")
        for p in await client.search(query):
            price = f"{p.price.amount / 100:.2f} {p.price.currency}"
            checkout = "native" if p.native_checkout else "-"
            print(f"- {p.shop.name} | {price} | checkout:{checkout} | {p.title[:50]}")
            print(f"    {p.description[:120]}")


asyncio.run(main())
