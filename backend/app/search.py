"""Turn a furniture slot (role + max footprint) into a catalog search query."""

from typing import Literal

Role = Literal["bed", "desk", "desk_chair", "dresser", "nightstand"]

SEARCH_LIMIT = 25  # handoff section 6: 25-50 per search
# Search hint only (not a fit rule): never ask for a bigger "desk 144 inch" than a bedroom piece.
QUERY_SIZE_CAP = {"desk": 60, "dresser": 48}


def build_query(role: Role, max_footprint: tuple[float, float]) -> str:
    """max_footprint is (width, depth) in inches.

    Wording is a placeholder from the handoff examples; M3 refines it.
    """
    width = int(min(max_footprint[0], QUERY_SIZE_CAP.get(role, max_footprint[0])))
    if role == "bed":
        return "twin xl bed frame"
    if role == "desk":
        return f"desk {width} inch"
    if role == "desk_chair":
        return "desk chair"
    if role == "dresser":
        return f"dresser {width} inch"
    return "nightstand"
