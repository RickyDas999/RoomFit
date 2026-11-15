"""Turn a furniture slot (role + max footprint) into a catalog search query."""

from typing import Literal

Role = Literal["bed", "desk", "desk_chair", "dresser", "nightstand"]

SEARCH_LIMIT = 25  # handoff section 6: 25-50 per search


def build_query(role: Role, max_footprint: tuple[float, float]) -> str:
    """max_footprint is (width, depth) in inches.

    Wording is a placeholder from the handoff examples; M3 refines it.
    """
    width = int(max_footprint[0])
    if role == "bed":
        return "twin xl bed frame"
    if role == "desk":
        return f"desk {width} inch"
    if role == "desk_chair":
        return "desk chair"
    if role == "dresser":
        return f"dresser {width} inch"
    return "nightstand"
