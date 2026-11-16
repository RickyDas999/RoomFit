"""Standard mattress sizes, used to pick a bed that suits the room (inches, width x length)."""

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
