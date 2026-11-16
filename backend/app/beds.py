"""Standard mattress sizes, used to pick a bed that suits the room (inches, width x length)."""

import re
from typing import Literal

BedSize = Literal["twin_xl", "full", "queen", "king"]
BedChoice = Literal["auto", "twin_xl", "full", "queen", "king"]

# Largest first. Twin XL is the smallest we offer (Ricky's call to confirm).
BED_SIZES: dict[BedSize, tuple[str, float, float]] = {
    "king": ("King", 76, 80),
    "queen": ("Queen", 60, 80),
    "full": ("Full", 54, 75),
    "twin_xl": ("Twin XL", 38, 80),
}


FRAME_EXTRA = 4.0  # a bed frame is about this much wider and longer than its mattress


def label(size: BedSize) -> str:
    return BED_SIZES[size][0]


def sizes_that_fit(max_along: float, max_across: float) -> list[BedSize]:
    """Sizes whose frame (mattress + FRAME_EXTRA) fits the bed slot, largest first."""
    return [
        s
        for s, (_, w, ln) in BED_SIZES.items()
        if ln + FRAME_EXTRA <= max_along and w + FRAME_EXTRA <= max_across
    ]


SIZE_SLACK = 2.0  # listings round and mix up length/width a little


def matches_size(size: BedSize, along: float, across: float) -> bool:
    """True if a frame this big could hold the mattress (a "king" listing 57 in wide is not a king)."""
    _, w, ln = BED_SIZES[size]
    return along + SIZE_SLACK >= ln and across + SIZE_SLACK >= w


# Mattress sizes by name, for checking a bed listing against its own title.
_TITLE_SIZES = {
    "california king": (72.0, 84.0),
    "king": (76.0, 80.0),
    "queen": (60.0, 80.0),
    "full xl": (54.0, 80.0),
    "full": (54.0, 75.0),
    "twin xl": (38.0, 80.0),
    "twin": (38.0, 75.0),
}
_TITLE_NAME = re.compile(
    r"\b(california king|cal king|king|queen(?!\s+anne)|full[\s-]*xl"
    r"|full(?=[\s-]*(?:size|bed|platform|frame))|twin[\s-]*xl|twin)\b",
    re.IGNORECASE,
)
_ANY_SIZE_WORD = re.compile(r"\b(?:king|queen(?!\s+anne)|full|twin)\b", re.IGNORECASE)
_BED_WORD = re.compile(r"\b(bed|bedframe|frame|platform)\b", re.IGNORECASE)
_NOT_A_BED = re.compile(
    r"\b(desk|dresser|nightstand|night stand|bedside|chair|table|bench|sofa|couch|mirror|"
    r"wardrobe|chest|vanity|armoire|ottoman)\b",
    re.IGNORECASE,
)


def title_size_mismatch(title: str, along: float, across: float) -> bool:
    """True if the title names exactly one bed size and the listed frame is smaller than its mattress.

    Titles that name several sizes ("Twin/Full/Queen"), none, or that are not about a bed
    (a desk, a nightstand set) are not checked.
    """
    if not _BED_WORD.search(title) or _NOT_A_BED.search(title):
        return False
    names = {
        "california king"
        if m.lower().startswith("cal")
        else re.sub(r"[\s-]+", " ", m.lower())
        for m in _TITLE_NAME.findall(title)
    }
    if len(names) != 1 or len(set(w.lower() for w in _ANY_SIZE_WORD.findall(title))) > 1:
        return False
    ml, mw = max(_TITLE_SIZES[next(iter(names))]), min(_TITLE_SIZES[next(iter(names))])
    long_side, short_side = max(along, across), min(along, across)
    return long_side + SIZE_SLACK < ml or short_side + SIZE_SLACK < mw
