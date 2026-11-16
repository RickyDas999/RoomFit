"""The agent profile URL and the profile file it points at."""

import json
import re
import subprocess
from pathlib import Path

import pytest

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


def test_the_pinned_commit_serves_the_same_profile_as_the_file() -> None:
    """Edit the profile and forget to move the pin, and Shopify keeps seeing the old one."""
    sha = re.search(r"@([0-9a-f]{7,40})/", PROFILE_URL)
    assert sha
    root = PROFILE.parents[1]
    try:
        pinned = subprocess.run(
            ["git", "show", f"{sha.group(1)}:agent-profile/ucp-profile.json"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
            timeout=20,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        pytest.skip(
            "the pinned commit is not in this clone (shallow checkout or no git)"
        )
    assert json.loads(pinned) == json.loads(PROFILE.read_text()), (
        "agent-profile/ucp-profile.json changed: commit it and point PROFILE_URL at the new commit"
    )
