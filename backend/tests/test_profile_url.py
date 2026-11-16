"""The agent profile URL and the profile file it points at."""

import json
import re
from pathlib import Path

from app.catalog import PROFILE_URL

PROFILE = Path(__file__).resolve().parents[2] / "agent-profile" / "ucp-profile.json"


def test_the_profile_url_is_pinned_to_a_commit_never_a_branch() -> None:
    # Shopify caches a profile by URL; a branch URL can serve an old copy for hours
    assert re.fullmatch(
        r"https://cdn\.jsdelivr\.net/gh/RickyDas999/RoomFit@[0-9a-f]{7,40}/agent-profile/ucp-profile\.json",
        PROFILE_URL,
    ), PROFILE_URL


def test_the_profile_declares_everything_the_app_calls() -> None:
    caps = json.loads(PROFILE.read_text())["ucp"]["capabilities"]
    for needed in (
        "dev.ucp.shopping.catalog.search",
        "dev.ucp.shopping.catalog.lookup",
        "dev.shopify.catalog.global",
        "dev.ucp.shopping.cart",  # create_cart / cancel_cart
        "dev.ucp.shopping.checkout",
    ):
        assert needed in caps
