"""Fit engine tests: every rule at its boundary, plus known-good and known-bad layouts."""

import pytest

from app.dimensions import Dimensions
from app.fit import evaluate_layout, evaluate_placed, orient, verdict_for
from app.room import SAMPLE_ROOM, Rect, plan_room
from app.search import Role

PLAN = plan_room(SAMPLE_ROOM)  # 144 x 192, lane x 54-90 / y 0-96, closet 0-48 x 0-24
GOOD: dict[Role, tuple[float, float]] = {
    "bed": (80, 40),
    "desk": (48, 24),
    "dresser": (36, 20),
    "nightstand": (18, 16),
}


def shorts(placed: dict[Role, Rect]) -> dict[str, float]:
    ev = evaluate_placed(PLAN, placed)
    return {f.rule: f.short_in for f in ev.hard_fails}


# --- known-good / known-bad layouts ---


def test_known_good_layout_fits() -> None:
    _, _, ev = evaluate_layout(SAMPLE_ROOM, GOOD)
    assert ev.hard_fails == []
    assert ev.missing_needs == []
    assert ev.verdict == "fits"
    assert ev.coverage_pct == pytest.approx(20.83, abs=0.01)
    assert ev.coverage_status == "ok"


def test_oversized_desk_breaks_behind_chair_by_six_inches() -> None:
    # the handoff example. (along, across) = (48, 54): a desk 54 in deep. Through the API a real
    # listing goes through orient(); see test_m3_review.py for that path.
    _, _, ev = evaluate_layout(SAMPLE_ROOM, {**GOOD, "desk": (48, 54)})
    assert [f.message for f in ev.hard_fails] == ["behind the desk chair: 6 in short"]
    assert ev.verdict == "cramped"


@pytest.mark.parametrize(("depth", "short"), [(52, 4), (53, 5), (54, 6)])
def test_desk_depth_shortfall_grows_one_for_one(depth: float, short: float) -> None:
    _, _, ev = evaluate_layout(SAMPLE_ROOM, {**GOOD, "desk": (48, depth)})
    assert [(f.rule, f.short_in) for f in ev.hard_fails] == [
        ("behind_desk_chair", short)
    ]


def test_bad_layout_reports_every_broken_rule() -> None:
    bad = {
        **GOOD,
        "desk": (48, 54),
        "dresser": (60, 30),
    }  # deep desk, and a dresser into the lane
    _, _, ev = evaluate_layout(SAMPLE_ROOM, bad)
    assert {f.rule: f.short_in for f in ev.hard_fails} == {
        "path_from_door": 6,
        "behind_desk_chair": 6,
    }
    assert ev.verdict == "cramped"


# --- boundaries: exactly at the limit passes, a hair under fails ---

CHAIR = Rect(x=24, y=158, w=20, d=20)
DESK = Rect(x=0, y=144, w=24, d=48)


@pytest.mark.parametrize(
    ("gap", "fails"), [(18, False), (18.0001, False), (17.9, True)]
)
def test_behind_desk_chair_boundary(gap: float, fails: bool) -> None:
    blocker = Rect(x=CHAIR.x2 + gap, y=150, w=20, d=40)  # stands behind the chair
    got = shorts({"desk": DESK, "desk_chair": CHAIR, "dresser": blocker})
    assert ("behind_desk_chair" in got) is fails
    if fails:
        assert got["behind_desk_chair"] == 0.1


@pytest.mark.parametrize(("gap", "fails"), [(24, False), (23.9, True)])
def test_bed_open_side_boundary(gap: float, fails: bool) -> None:
    bed = Rect(x=104, y=112, w=40, d=80)  # right wall: only the left side is open
    blocker = Rect(x=bed.x - gap - 10, y=120, w=10, d=10)
    got = shorts({"bed": bed, "dresser": blocker})
    assert ("bed_open_side" in got) is fails
    if fails:
        assert got["bed_open_side"] == 0.1


def test_twin_may_sit_against_a_wall_one_open_side_is_enough() -> None:
    bed = Rect(x=104, y=112, w=40, d=80)  # wall on the right, open on the left
    assert "bed_open_side" not in shorts({"bed": bed})


def test_bed_with_no_open_side_fails_by_the_full_clearance() -> None:
    bed = Rect(x=0, y=0, w=144, d=190)  # wall to wall, running up and down
    assert shorts({"bed": bed})["bed_open_side"] == 24


def test_nightstand_beside_bed_head_does_not_block_the_open_side() -> None:
    bed = Rect(x=104, y=112, w=40, d=80)
    ns = Rect(x=86, y=176, w=18, d=16)
    assert "bed_open_side" not in shorts({"bed": bed, "nightstand": ns})


@pytest.mark.parametrize(("gap", "fails"), [(24, False), (23.9, True)])
def test_in_front_of_dresser_boundary(gap: float, fails: bool) -> None:
    dresser = Rect(x=108, y=0, w=36, d=20)  # top wall, faces down
    blocker = Rect(x=100, y=dresser.y2 + gap, w=44, d=40)
    got = shorts({"dresser": dresser, "bed": blocker})
    assert ("in_front_of_dresser" in got) is fails
    if fails:
        assert got["in_front_of_dresser"] == 0.1


@pytest.mark.parametrize(("gap", "fails"), [(24, False), (23.9, True)])
def test_in_front_of_closet_boundary(gap: float, fails: bool) -> None:
    blocker = Rect(x=0, y=24 + gap, w=24, d=40)  # closet is x 0-48, y 0-24, faces down
    got = shorts({"desk": blocker})
    assert ("in_front_of_closet" in got) is fails
    if fails:
        assert got["in_front_of_closet"] == 0.1


@pytest.mark.parametrize(("x", "short"), [(90, None), (89, 1), (82, 8), (54, 36)])
def test_path_from_door_boundary(x: float, short: float | None) -> None:
    piece = Rect(x=x, y=40, w=20, d=20)  # inside the lane's y range (0-96)
    got = shorts({"dresser": piece})
    if short is None:
        assert "path_from_door" not in got
    else:
        assert got["path_from_door"] == min(
            short, 20
        )  # the lane is narrowed by the overlap


def test_furniture_below_the_path_end_is_fine() -> None:
    piece = Rect(x=60, y=100, w=20, d=20)  # lane ends at y = 96 (center line)
    assert "path_from_door" not in shorts({"dresser": piece})


def test_overlap_and_outside_room_are_hard_fails() -> None:
    a = Rect(x=104, y=112, w=40, d=80)
    b = Rect(x=100, y=150, w=20, d=20)
    assert shorts({"bed": a, "nightstand": b})["overlap"] == 16
    assert shorts({"bed": Rect(x=130, y=112, w=40, d=80)})["outside_room"] == 26


def test_floor_pieces_must_not_overlap_the_closet() -> None:
    assert shorts({"desk": Rect(x=0, y=0, w=24, d=48)})["overlap"] == 24


# --- soft rule and needs ---


def area_rect(area: float) -> Rect:
    return Rect(x=0, y=0, w=area / 100, d=100)


@pytest.mark.parametrize(
    ("pct", "status"),
    [(39.9, "ok"), (40.0, "ok"), (40.1, "warn"), (45.0, "warn"), (45.1, "flag")],
)
def test_coverage_thresholds(pct: float, status: str) -> None:
    room_area = 144 * 192
    ev = evaluate_placed(PLAN, {"bed": area_rect(room_area * pct / 100)})
    assert ev.coverage_status == status


def test_missing_needs() -> None:
    _, _, ev = evaluate_layout(SAMPLE_ROOM, {})
    assert ev.missing_needs == ["sleep", "study"]  # the closet covers storage
    assert ev.verdict == "incomplete"
    _, _, ev = evaluate_layout(SAMPLE_ROOM, {"bed": (80, 40), "dresser": (36, 20)})
    assert ev.missing_needs == ["study"]


def test_closet_counts_as_storage_only_when_there_is_one() -> None:
    room = SAMPLE_ROOM.model_copy(update={"closet": None})
    _, _, ev = evaluate_layout(room, {"bed": (80, 40), "desk": (48, 24)})
    assert ev.missing_needs == ["storage"]


def test_chair_follows_the_desk() -> None:
    _, placed, _ = evaluate_layout(SAMPLE_ROOM, {"desk": (48, 24)})
    assert "desk_chair" in placed  # chair is assumed 20 x 20 and appears with the desk
    assert placed["desk_chair"].w == placed["desk_chair"].d == 20


@pytest.mark.parametrize(
    ("fail", "missing", "cov", "expected"),
    [
        (True, [], 10, "cramped"),
        (True, ["sleep"], 10, "cramped"),  # a hard fail wins over incomplete
        (False, ["sleep"], 10, "incomplete"),
        (False, ["sleep"], 50, "incomplete"),
        (False, [], 40, "fits"),
        (False, [], 40.01, "cramped"),
        (False, [], 0, "fits"),
    ],
)
def test_verdict(fail: bool, missing: list[str], cov: float, expected: str) -> None:
    assert verdict_for(fail, missing, cov) == expected


def test_orient_puts_the_long_side_along_the_wall() -> None:
    assert orient(Dimensions(w=40.1, d=81.4)) == (81.4, 40.1)
    assert orient(Dimensions(w=81.4, d=40.1)) == (81.4, 40.1)


# --- turned pieces: the clearance follows the piece, not the screen axes ---


def test_a_bed_turned_across_the_room_needs_its_open_side_above_or_below() -> None:
    # runs left to right along the bottom wall: its long sides face up (free) and down (the wall)
    turned = Rect(x=60, y=152, w=80, d=40)
    assert "bed_open_side" not in shorts({"bed": turned})  # 152 in free above it
    from app.fit import zones_for

    zone = next(
        z
        for z in zones_for(
            PLAN, {"bed": turned}, evaluate_placed(PLAN, {"bed": turned})
        )
        if z.rule == "bed_open_side"
    )
    assert (
        zone.rect.y2 == 152 and zone.rect.w == 80
    )  # shaded above the bed, along its long side


def test_a_turned_bed_with_both_long_sides_blocked_fails() -> None:
    turned = Rect(x=60, y=100, w=80, d=40)
    above = Rect(x=60, y=90, w=80, d=10)  # a wall of furniture right above it
    below = Rect(x=60, y=140, w=80, d=10)  # and right below it
    assert (
        shorts({"bed": turned, "desk": above, "dresser": below})["bed_open_side"] == 24
    )


def test_a_turned_bed_is_not_failed_for_tight_ends() -> None:
    # the same bed upright with 4 in on each long side would fail; turned, its ends are the 4 in
    upright = Rect(x=4, y=100, w=40, d=80)
    wall_r = Rect(x=44 + 4, y=100, w=96, d=80)  # blocks the right side 4 in away
    assert shorts({"bed": upright, "dresser": wall_r}).get("bed_open_side") == 20


def test_a_turned_dresser_needs_clearance_at_its_side_not_below() -> None:
    from app.fit import zones_for

    turned = Rect(x=100, y=0, w=20, d=60)  # long side against... sticking down the room
    ev = evaluate_placed(PLAN, {"dresser": turned})
    assert "in_front_of_dresser" not in {
        f.rule for f in ev.hard_fails
    }  # open on its left/right
    assert any(
        z.rule == "in_front_of_dresser"
        for z in zones_for(PLAN, {"dresser": turned}, ev)
    )
    boxed = [Rect(x=76, y=0, w=24, d=60), Rect(x=120, y=0, w=24, d=60)]
    ev2 = evaluate_placed(
        PLAN, {"dresser": turned, "desk": boxed[0], "nightstand": boxed[1]}
    )
    assert any(f.rule == "in_front_of_dresser" for f in ev2.hard_fails)
