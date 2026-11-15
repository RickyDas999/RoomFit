"""Dev only: how many live products have parseable dimensions? Prints; writes nothing.

Run from backend/:  python -m scripts.dimension_report
"""

import asyncio
from collections import Counter

from app.catalog import CatalogClient
from app.search import build_query
from scripts.dev_catalog import FOOTPRINTS, load_env


async def main() -> None:
    load_env()
    client = CatalogClient.from_env()
    total = parsed = 0
    for role, footprint in FOOTPRINTS.items():
        products = await client.search(build_query(role, footprint))
        n_ok = sum(p.dimension_status == "parsed" for p in products)
        why = Counter(
            p.dimension_reason for p in products if p.dimension_status != "parsed"
        )
        print(
            f"{role:11} {n_ok} of {len(products)} had parseable dimensions   not parsed: {dict(why)}"
        )
        total, parsed = total + len(products), parsed + n_ok
    print(f"\nTOTAL: {parsed} of {total} products had parseable dimensions")


if __name__ == "__main__":
    asyncio.run(main())
