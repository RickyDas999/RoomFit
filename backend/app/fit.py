"""Fit engine: place products in slots and check every rule from the handoff.

Pure functions over rectangles in the canonical frame (door on top), see room.py.
A product's footprint is (along, across) = (longer side, shorter side).
"""

from typing import Literal

from pydantic import BaseModel

from app.dimensions import Dimensions
from app.room import Plan, Rect, Room, SlotPlan, plan_room
from app.rules import (
    BED_OPEN_SIDE,
    CHAIR_ASSUMED,
    CHAIR_BACK,
    COVERAGE_FLAG,
    COVERAGE_WARN,
    EPS,
    FRONT_CLEARANCE,
)
from app.search import Role

Footprints = dict[Role, tuple[float, float]]
Verdict = Literal["fits", "cramped", "incomplete"]

NAMES = {
    "bed": "bed",
    "desk": "desk",
    "desk_chair": "desk chair",
    "dresser": "dresser",
    "nightstand": "nightstand",
    "closet": "closet",
}


class HardFail(BaseModel):
    rule: Literal[
        "path_from_door",
        "bed_open_side",
        "in_front_of_dresser",
        "in_front_of_closet",
        "behind_desk_chair",
        "overlap",
        "outside_room",
    ]
    pieces: list[str]
    short_in: float
    message: str


class Evaluation(BaseModel):
    hard_fails: list[HardFail]
    coverage_pct: float
    coverage_status: Literal["ok", "warn", "flag"]
    missing_needs: list[str]
    verdict: Verdict


class Zone(BaseModel):
    """A clearance area the UI can shade: red when `broken`, with how far short it is."""

    rule: Literal[
        "path_from_door",
        "bed_open_side",
        "in_front_of_dresser",
        "in_front_of_closet",
        "behind_desk_chair",
    ]
    rect: Rect
    broken: bool
    short_in: float


def orient(d: Dimensions) -> tuple[float, float]:
    """(along, across): the long side runs along the wall. Rotation is tried in M5."""
    return max(d.w, d.d), min(d.w, d.d)


def orientations(d: Dimensions) -> list[tuple[float, float]]:
    """Both ways to stand a piece: long side along the wall first, then turned 90 degrees."""
    a, b = orient(d)
    return [(a, b)] if a == b else [(a, b), (b, a)]


def _box(
    sp: SlotPlan, along: float, across: float, origin: tuple[float, float] | None = None
) -> Rect:
    ox, oy = origin or sp.origin
    w, d = (across, along) if sp.along_axis == "y" else (along, across)
    if sp.along_axis == "y":
        x = ox if sp.across_dir > 0 else ox - w
        y = oy if sp.along_dir > 0 else oy - d
    else:
        x = ox if sp.along_dir > 0 else ox - w
        y = oy if sp.across_dir > 0 else oy - d
    return Rect(x=x, y=y, w=w, d=d)


def place_all(plan: Plan, fp: Footprints) -> dict[Role, Rect]:
    """Snap each footprint to its slot. Nightstand hugs the bed; chair sits in front of the desk."""
    placed: dict[Role, Rect] = {}
    for role in ("bed", "dresser"):
        if role in fp:
            placed[role] = _box(plan.slots[role], *fp[role])
    if "desk" in fp:
        placed["desk"] = _box(plan.slots["desk"], *fp["desk"])
    if "nightstand" in fp:
        sp = plan.slots["nightstand"]
        origin = sp.origin
        if "bed" in placed:  # beside the bed's open edge
            bed = placed["bed"]
            origin = (bed.x if plan.bed_side == "right" else bed.x2, sp.origin[1])
        placed["nightstand"] = _box(sp, *fp["nightstand"], origin=origin)
    if "desk" in placed:
        desk, (cw, cd) = placed["desk"], CHAIR_ASSUMED
        if plan.desk_on_top:  # chair below the desk, centered
            x = min(max(desk.x + (desk.w - cw) / 2, 0.0), plan.W - cw)
            placed["desk_chair"] = Rect(x=x, y=desk.y2, w=cw, d=cd)
            return placed
        on_left = plan.slots["desk"].across_dir > 0
        y = min(max(desk.y + (desk.d - cd) / 2, 0.0), plan.D - cd)  # stay inside the room
        placed["desk_chair"] = Rect(x=desk.x2 if on_left else desk.x - cw, y=y, w=cw, d=cd)
    return placed


def _free(r: Rect, direction: str, obstacles: list[Rect], W: float, D: float) -> float:
    """Open distance from `r` in `direction` ("+x", "-x", "+y", "-y") to the nearest obstacle or wall."""
    horiz = direction[1] == "x"
    plus = direction[0] == "+"
    best = (W - r.x2 if plus else r.x) if horiz else (D - r.y2 if plus else r.y)
    for o in obstacles:
        if horiz:
            if not (o.y < r.y2 - EPS and o.y2 > r.y + EPS):
                continue
            gap = o.x - r.x2 if plus else r.x - o.x2
            ahead = o.x >= r.x2 - EPS if plus else o.x2 <= r.x + EPS
        else:
            if not (o.x < r.x2 - EPS and o.x2 > r.x + EPS):
                continue
            gap = o.y - r.y2 if plus else r.y - o.y2
            ahead = o.y >= r.y2 - EPS if plus else o.y2 <= r.y + EPS
        if ahead:
            best = min(best, gap)
    return max(best, 0.0)


def _fail(rule: str, pieces: list[str], short: float, text: str) -> HardFail:
    short = round(short, 2)
    return HardFail.model_validate(
        {"rule": rule, "pieces": pieces, "short_in": short, "message": text.format(short=f"{short:g}")}
    )


def verdict_for(has_hard_fail: bool, missing: list[str], coverage_pct: float) -> Verdict:
    """Hard fail -> cramped; else a missing need -> incomplete; else over the warn line -> cramped."""
    if has_hard_fail:
        return "cramped"
    if missing:
        return "incomplete"
    return "cramped" if coverage_pct > COVERAGE_WARN else "fits"


def evaluate_placed(plan: Plan, placed: dict[Role, Rect]) -> Evaluation:
    W, D = plan.W, plan.D
    fails: list[HardFail] = []
    pieces: dict[str, Rect] = {str(k): v for k, v in placed.items()}
    if plan.closet:
        pieces["closet"] = plan.closet

    # pieces must be inside the room and must not overlap each other or the closet
    names = list(pieces)
    for i, a in enumerate(names):
        r = pieces[a]
        out = max(-r.x, -r.y, r.x2 - W, r.y2 - D, 0.0)
        if out > EPS:
            fails.append(
                _fail("outside_room", [a], out, f"{NAMES[a]} sticks out of the room by {{short}} in")
            )
        for b in names[i + 1 :]:
            ox, oy = r.overlap(pieces[b])
            if ox > EPS and oy > EPS:
                fails.append(
                    _fail(
                        "overlap", [a, b], min(ox, oy), f"{NAMES[a]} overlaps {NAMES[b]} by {{short}} in"
                    )
                )

    # clear path from the door: furniture must not narrow the lane
    for name, r in pieces.items():
        ox, oy = r.overlap(plan.lane)
        if ox > EPS and oy > EPS:
            fails.append(_fail("path_from_door", [name], ox, "clear path from the door: {short} in short"))

    def obstacles_for(name: str) -> list[Rect]:
        return [r for n, r in pieces.items() if n != name]

    if "bed" in placed:  # one open long side is enough (a twin may sit against a wall)
        # the nightstand at the bed's head does not count as blocking the open side
        bed = placed["bed"]
        obs = [r for n, r in pieces.items() if n not in ("bed", "nightstand")]
        best = max(_free(bed, "-x", obs, W, D), _free(bed, "+x", obs, W, D))
        if best + EPS < BED_OPEN_SIDE:
            fails.append(
                _fail("bed_open_side", ["bed"], BED_OPEN_SIDE - best, "open side of the bed: {short} in short")
            )
    if "dresser" in placed:  # the dresser stands on the top wall and faces down
        free = _free(placed["dresser"], "+y", obstacles_for("dresser"), W, D)
        if free + EPS < FRONT_CLEARANCE:
            fails.append(
                _fail(
                    "in_front_of_dresser",
                    ["dresser"],
                    FRONT_CLEARANCE - free,
                    "in front of the dresser: {short} in short",
                )
            )
    if plan.closet:
        free = _free(plan.closet, plan.closet_front_dir, obstacles_for("closet"), W, D)
        if free + EPS < FRONT_CLEARANCE:
            fails.append(
                _fail(
                    "in_front_of_closet",
                    ["closet"],
                    FRONT_CLEARANCE - free,
                    "in front of the closet: {short} in short",
                )
            )
    if "desk_chair" in placed:  # behind the chair = away from the desk
        away = "+y" if plan.desk_on_top else "+x" if plan.slots["desk"].across_dir > 0 else "-x"
        free = _free(placed["desk_chair"], away, obstacles_for("desk_chair"), W, D)
        if free + EPS < CHAIR_BACK:
            fails.append(
                _fail(
                    "behind_desk_chair",
                    ["desk_chair", "desk"],
                    CHAIR_BACK - free,
                    "behind the desk chair: {short} in short",
                )
            )

    coverage = sum(r.area for r in placed.values()) / (W * D) * 100
    status: Literal["ok", "warn", "flag"] = (
        "flag" if coverage > COVERAGE_FLAG else "warn" if coverage > COVERAGE_WARN else "ok"
    )
    missing = []
    if "bed" not in placed:
        missing.append("sleep")
    if "desk" in plan.needs and ("desk" not in placed or "desk_chair" not in placed):
        missing.append("study")
    if "dresser" in plan.needs and "dresser" not in placed and plan.closet is None:
        missing.append("storage")
    return Evaluation(
        hard_fails=fails,
        coverage_pct=round(coverage, 2),
        coverage_status=status,
        missing_needs=missing,
        verdict=verdict_for(bool(fails), missing, coverage),
    )


def zones_for(plan: Plan, placed: dict[Role, Rect], ev: Evaluation) -> list[Zone]:
    """Clearance rectangles (canonical frame) for everything placed, plus the door path.

    Each rectangle is clipped to the room; one that falls entirely outside is dropped.
    """
    short: dict[str, float] = {}
    for f in ev.hard_fails:
        short[f.rule] = max(short.get(f.rule, 0.0), f.short_in)
    zones: list[Zone] = []

    def add(rule: str, r: Rect) -> None:
        x, y = max(r.x, 0.0), max(r.y, 0.0)
        clipped = Rect(x=x, y=y, w=min(r.x2, plan.W) - x, d=min(r.y2, plan.D) - y)
        if clipped.w > EPS and clipped.d > EPS:
            zones.append(
                Zone.model_validate(
                    {"rule": rule, "rect": clipped, "broken": rule in short, "short_in": short.get(rule, 0.0)}
                )
            )

    add("path_from_door", plan.lane)
    if "bed" in placed:  # shade the more open long side
        bed = placed["bed"]
        obs = [r for n, r in placed.items() if n not in ("bed", "nightstand")]
        if plan.closet:
            obs.append(plan.closet)
        left = _free(bed, "-x", obs, plan.W, plan.D)
        right = _free(bed, "+x", obs, plan.W, plan.D)
        x = bed.x - BED_OPEN_SIDE if left >= right else bed.x2
        add("bed_open_side", Rect(x=x, y=bed.y, w=BED_OPEN_SIDE, d=bed.d))
    if "dresser" in placed:
        d = placed["dresser"]
        add("in_front_of_dresser", Rect(x=d.x, y=d.y2, w=d.w, d=FRONT_CLEARANCE))
    if plan.closet_front:
        add("in_front_of_closet", plan.closet_front)
    if "desk_chair" in placed:
        c = placed["desk_chair"]
        behind_right = plan.slots["desk"].across_dir > 0  # desk on the left wall: behind = +x
        if plan.desk_on_top:  # desk on the door wall: behind the chair = below it
            add("behind_desk_chair", Rect(x=c.x, y=c.y2, w=c.w, d=CHAIR_BACK))
        else:
            add("behind_desk_chair", Rect(x=c.x2 if behind_right else c.x - CHAIR_BACK, y=c.y, w=CHAIR_BACK, d=c.d))
    return zones


def evaluate_layout(room: Room, fp: Footprints) -> tuple[Plan, dict[Role, Rect], Evaluation]:
    plan = plan_room(room)
    placed = place_all(plan, fp)
    return plan, placed, evaluate_placed(plan, placed)
