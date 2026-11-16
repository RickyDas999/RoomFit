"""The storyboard moments the video relies on, pinned with sizes taken from the live catalog.

Moment 3: "swap in a bigger desk and the 18 in chair-clearance flag fires". In the 12 x 16 ft sample
room the biggest real desk (a 60 x 60 in L-shape) only breaks the bed's open side. In the 10 x 16 ft
"Narrow bedroom" example it breaks the chair clearance too, which is the moment to record.
"""

from app.fit import evaluate_layout
from app.room import SAMPLE_ROOM, Door, Room, Window
from app.search import Role

# listed sizes of real products (long side first), as the engine sees them
LAYOUT: dict[Role, tuple[float, float]] = {
    "bed": (82.2, 41.0),
    "dresser": (28.0, 26.4),
    "nightstand": (15.7, 11.8),
}
SMALL_DESK = (60.0, 22.0)
L_SHAPED_DESK = (60.0, 60.0)

NARROW = Room(
    width=124,
    depth=192,
    door=Door(wall="top", offset=46, width=32),
    window=Window(wall="bottom", offset=38, width=48),
)


def rules(room: Room, desk: tuple[float, float]) -> set[str]:
    return {f.rule for f in evaluate_layout(room, {**LAYOUT, "desk": desk})[2].hard_fails}


def test_moment_1_the_demo_room_is_about_200_square_feet() -> None:
    assert SAMPLE_ROOM.width * SAMPLE_ROOM.depth / 144 == 192  # 12 x 16 ft


def test_moment_3_in_the_narrow_bedroom_the_cheap_desk_fits_and_the_big_desk_breaks_the_chair_rule() -> None:
    ev = evaluate_layout(NARROW, {**LAYOUT, "desk": SMALL_DESK})[2]
    assert ev.hard_fails == [] and ev.verdict == "fits"
    ev = evaluate_layout(NARROW, {**LAYOUT, "desk": L_SHAPED_DESK})[2]
    assert "behind_desk_chair" in {f.rule for f in ev.hard_fails}
    chair = next(f for f in ev.hard_fails if f.rule == "behind_desk_chair")
    assert chair.short_in > 0 and "behind the desk chair" in chair.message
    assert ev.verdict == "cramped"


def test_in_the_sample_room_the_big_desk_breaks_the_bed_side_but_not_the_chair_rule() -> None:
    # why the narrow example exists: say this in the video only for the narrow room
    assert rules(SAMPLE_ROOM, SMALL_DESK) == set()
    assert "behind_desk_chair" not in rules(SAMPLE_ROOM, L_SHAPED_DESK)
