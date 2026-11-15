import pytest

from app.fit import evaluate_layout
from app.room import SAMPLE_ROOM, Door, Frame, Rect, Room, plan_room, public_slots


def maxes(room: Room) -> dict[str, tuple[float, float]]:
    return {s.role: s.max_footprint for s in public_slots(room)}


def test_sample_room_slots() -> None:
    p = plan_room(SAMPLE_ROOM)
    assert (p.lane.x, p.lane.w, p.lane.d) == (
        54,
        36,
        96,
    )  # 36 in lane, to the center line
    assert p.bed_side == "right"
    assert maxes(SAMPLE_ROOM) == {
        "bed": (96, 54),
        "desk": (96, 52),
        "desk_chair": (20, 20),
        "dresser": (54, 72),
        "nightstand": (36, 96),
    }
    assert all(s.fits for s in public_slots(SAMPLE_ROOM))


def test_chair_slot_is_flagged_as_assumed() -> None:
    chair = next(s for s in public_slots(SAMPLE_ROOM) if s.role == "desk_chair")
    assert chair.assumed_footprint is True


@pytest.mark.parametrize("wall", ["top", "bottom", "left", "right"])
def test_frame_round_trips_rects(wall: str) -> None:
    room = SAMPLE_ROOM.model_copy(update={"door": Door(wall=wall, offset=56, width=32)})  # type: ignore[arg-type]
    fr = Frame(room)
    r = Rect(x=10, y=20, w=30, d=15)
    back = fr.rect_back(fr.rect_fwd(r))
    assert (back.x, back.y, back.w, back.d) == pytest.approx((10, 20, 30, 15))


def rotated(wall: str) -> Room:
    """The sample room with the door on another wall (same physical room, turned)."""
    if wall == "bottom":
        return Room(
            width=144,
            depth=192,
            door=Door(wall="bottom", offset=56, width=32),
            closet=Rect(x=0, y=168, w=48, d=24),
        )
    if wall == "left":
        return Room(
            width=192,
            depth=144,
            door=Door(wall="left", offset=56, width=32),
            closet=Rect(x=0, y=0, w=24, d=48),
        )
    return Room(
        width=192,
        depth=144,
        door=Door(wall="right", offset=56, width=32),
        closet=Rect(x=168, y=0, w=24, d=48),
    )


@pytest.mark.parametrize("wall", ["bottom", "left", "right"])
def test_any_door_wall_gives_the_same_slots(wall: str) -> None:
    assert maxes(rotated(wall)) == maxes(SAMPLE_ROOM)


@pytest.mark.parametrize("wall", ["bottom", "left", "right"])
def test_any_door_wall_evaluates_the_same(wall: str) -> None:
    good = {
        "bed": (80, 40),
        "desk": (48, 24),
        "dresser": (36, 20),
        "nightstand": (18, 16),
    }
    _, _, base = evaluate_layout(SAMPLE_ROOM, good)  # type: ignore[arg-type]
    _, _, ev = evaluate_layout(rotated(wall), good)  # type: ignore[arg-type]
    assert ev == base


def test_slot_regions_come_back_in_the_rooms_own_coordinates() -> None:
    room = rotated("left")  # 192 wide, 144 deep
    for s in public_slots(room):
        if s.region.area:
            assert (
                s.region.x >= 0
                and s.region.x2 <= 192
                and s.region.y >= 0
                and s.region.y2 <= 144
            )


def test_door_near_a_corner_keeps_the_lane_inside_the_room() -> None:
    room = SAMPLE_ROOM.model_copy(update={"door": Door(wall="top", offset=0, width=32)})
    p = plan_room(room)
    assert p.lane.x == 0 and p.lane.x2 == 36
    assert p.bed_side == "right"  # more room on the right


def test_tiny_room_has_slots_that_cannot_hold_anything_useful() -> None:
    room = Room(width=40, depth=50, door=Door(wall="top", offset=4, width=32))
    slots = {s.role: s for s in public_slots(room)}
    assert (
        not slots["desk"].fits
        and slots["desk"].note == "no desk fits under these rules"
    )
    assert not slots["desk_chair"].fits  # no desk, no chair
    assert slots["bed"].max_footprint[0] <= 25


def test_closet_inside_a_slot_region_shrinks_it() -> None:
    # closet in the bed's corner: the bed region must stop short of it
    room = SAMPLE_ROOM.model_copy(update={"closet": Rect(x=100, y=150, w=44, d=42)})
    bed = next(s for s in public_slots(room) if s.role == "bed")
    assert bed.max_footprint[0] < 96


@pytest.mark.parametrize(
    "bad",
    [
        {"door": Door(wall="top", offset=130, width=32)},  # runs off the wall
        {"closet": Rect(x=130, y=0, w=48, d=24)},  # sticks out
        {"width": 0},
    ],
)
def test_invalid_rooms_are_rejected(bad: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        SAMPLE_ROOM.model_copy(update=bad).model_validate(
            SAMPLE_ROOM.model_copy(update=bad).model_dump()
        )
