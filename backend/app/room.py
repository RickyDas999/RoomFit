"""Room model and slot planning.

All planning happens in a canonical frame where the door is on the TOP wall
(x right, y down, origin top-left). Any room is flipped/transposed into that
frame, planned, and mapped back for output.

Furniture convention: "along" is the long side (runs along the wall), "across"
is the short side (sticks out into the room). Rotation is tried in M5.
"""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.rules import (
    CHAIR_ASSUMED,
    CHAIR_BACK,
    EPS,
    FRONT_CLEARANCE,
    PATH_END_FRACTION,
    PATH_WIDTH,
)
from app.search import Role

Wall = Literal["top", "bottom", "left", "right"]


class Rect(BaseModel):
    x: float
    y: float
    w: float  # extent along x
    d: float  # extent along y

    @property
    def x2(self) -> float:
        return self.x + self.w

    @property
    def y2(self) -> float:
        return self.y + self.d

    @property
    def area(self) -> float:
        return max(self.w, 0.0) * max(self.d, 0.0)

    def overlap(self, o: "Rect") -> tuple[float, float]:
        return min(self.x2, o.x2) - max(self.x, o.x), min(self.y2, o.y2) - max(
            self.y, o.y
        )

    def intersects(self, o: "Rect") -> bool:
        ox, oy = self.overlap(o)
        return ox > EPS and oy > EPS


class Door(BaseModel):
    wall: Wall
    offset: float = Field(
        ge=0
    )  # from the wall's start (left or top) to the door's near edge
    width: float = Field(gt=0)
    swing: Literal["in", "out"] = "in"


class Window(BaseModel):
    wall: Wall
    offset: float = Field(ge=0)
    width: float = Field(gt=0)


class Room(BaseModel):
    width: float = Field(gt=0)  # x extent
    depth: float = Field(gt=0)  # y extent
    door: Door
    window: Window | None = None
    closet: Rect | None = None  # fixed, not for sale

    @model_validator(mode="after")
    def _inside(self) -> "Room":
        for name, item in (("door", self.door), ("window", self.window)):
            if item is None:
                continue
            length = self.width if item.wall in ("top", "bottom") else self.depth
            if item.offset + item.width > length + EPS:
                raise ValueError(f"{name} does not fit on the {item.wall} wall")
        c = self.closet
        if c and (
            c.w <= 0
            or c.d <= 0
            or c.x < 0
            or c.y < 0
            or c.x2 > self.width
            or c.y2 > self.depth
        ):
            raise ValueError("closet must be inside the room")
        return self


# Ricky, Nov 15: 12 x 16 ft, door centered on the top short wall, window opposite, 24 in closet.
SAMPLE_ROOM = Room(
    width=144,
    depth=192,
    door=Door(wall="top", offset=56, width=32),
    window=Window(wall="bottom", offset=48, width=48),
    closet=Rect(x=0, y=0, w=48, d=24),
)


class Frame:
    """Maps a room to the canonical frame (door on top) and back."""

    def __init__(self, room: Room) -> None:
        self.wall = room.door.wall
        self.rw, self.rd = room.width, room.depth
        sideways = self.wall in ("left", "right")
        self.W, self.D = (
            (room.depth, room.width) if sideways else (room.width, room.depth)
        )

    def fwd(self, x: float, y: float) -> tuple[float, float]:
        if self.wall == "top":
            return x, y
        if self.wall == "bottom":
            return x, self.rd - y
        if self.wall == "left":
            return y, x
        return y, self.rw - x  # right

    def back(self, x: float, y: float) -> tuple[float, float]:
        if self.wall == "top":
            return x, y
        if self.wall == "bottom":
            return x, self.rd - y
        if self.wall == "left":
            return y, x
        return self.rw - y, x  # right

    def _rect(self, r: Rect, *, forward: bool) -> Rect:
        move = self.fwd if forward else self.back
        (ax, ay), (bx, by) = move(r.x, r.y), move(r.x2, r.y2)
        return Rect(x=min(ax, bx), y=min(ay, by), w=abs(bx - ax), d=abs(by - ay))

    def rect_fwd(self, r: Rect) -> Rect:
        return self._rect(r, forward=True)

    def rect_back(self, r: Rect) -> Rect:
        return self._rect(r, forward=False)


@dataclass
class SlotPlan:
    role: Role
    region: Rect  # canonical; the space this slot may use
    along_axis: Literal["x", "y"]
    origin: tuple[float, float]  # canonical corner the piece snaps to
    along_dir: int  # +1 / -1: direction the long side extends from the origin
    across_dir: int  # +1 / -1: direction the short side extends from the origin
    max_along: float
    max_across: float

    @property
    def fits(self) -> bool:
        return self.max_along > EPS and self.max_across > EPS


@dataclass
class Plan:
    frame: Frame
    W: float
    D: float
    lane: Rect  # the clear path from the door (canonical)
    closet: Rect | None
    closet_front: Rect | None
    closet_front_dir: str  # "+y" | "-y" | "+x" | "-x": which way the closet faces
    bed_side: Literal["left", "right"]
    slots: dict[Role, SlotPlan]


class Slot(BaseModel):
    """A slot as the API returns it (original room coordinates)."""

    id: str
    role: Role
    region: Rect
    max_footprint: tuple[float, float]  # (along, across) in inches
    fits: bool
    assumed_footprint: bool = False  # desk chair: footprint is an assumption
    note: str | None = None


def _avoid(region: Rect, anchor_x: int, anchor_y: int, obstacles: list[Rect]) -> Rect:
    """Shrink `region` (kept anchored at one corner) until it clears every obstacle.

    anchor_x / anchor_y: -1 = anchored at the min edge, +1 = at the max edge.
    """
    r = region
    for _ in range(12):
        hit = next((o for o in obstacles if r.intersects(o)), None)
        if hit is None:
            return r
        if anchor_x < 0:
            a = Rect(x=r.x, y=r.y, w=hit.x - r.x, d=r.d)
        else:
            a = Rect(x=hit.x2, y=r.y, w=r.x2 - hit.x2, d=r.d)
        if anchor_y < 0:
            b = Rect(x=r.x, y=r.y, w=r.w, d=hit.y - r.y)
        else:
            b = Rect(x=r.x, y=hit.y2, w=r.w, d=r.y2 - hit.y2)
        best = max((a, b), key=lambda c: c.area)
        if best.area <= EPS:
            return Rect(x=r.x, y=r.y, w=0, d=0)
        r = best
    return r


def _closet_front(c: Rect, W: float, D: float) -> tuple[Rect, str]:
    """The 24 in in front of the closet: on the side away from the wall it stands against.

    A wide closet faces up/down, a tall one left/right (so a tall closet in a corner is
    read as a side-wall closet).
    """
    f = FRONT_CLEARANCE
    if c.d > c.w:  # tall closet: try the side walls first
        if c.x <= EPS:
            return Rect(x=c.x2, y=c.y, w=f, d=c.d), "+x"
        if c.x2 >= W - EPS:
            return Rect(x=c.x - f, y=c.y, w=f, d=c.d), "-x"
    if c.y <= EPS:
        return Rect(x=c.x, y=c.y2, w=c.w, d=f), "+y"
    if c.y2 >= D - EPS:
        return Rect(x=c.x, y=c.y - f, w=c.w, d=f), "-y"
    if c.x <= EPS:
        return Rect(x=c.x2, y=c.y, w=f, d=c.d), "+x"
    if c.x2 >= W - EPS:
        return Rect(x=c.x - f, y=c.y, w=f, d=c.d), "-x"
    return Rect(x=c.x, y=c.y2, w=c.w, d=f), "+y"


def plan_room(room: Room) -> Plan:
    fr = Frame(room)
    W, D = fr.W, fr.D

    # door span in the canonical frame
    d = room.door
    ends = {
        "top": ((d.offset, 0), (d.offset + d.width, 0)),
        "bottom": ((d.offset, room.depth), (d.offset + d.width, room.depth)),
        "left": ((0, d.offset), (0, d.offset + d.width)),
        "right": ((room.width, d.offset), (room.width, d.offset + d.width)),
    }[d.wall]
    cx0, cx1 = sorted(fr.fwd(*p)[0] for p in ends)
    door_center = (cx0 + cx1) / 2

    lane_w = min(max(PATH_WIDTH, d.width), W)
    lane_x = min(max(door_center - lane_w / 2, 0.0), W - lane_w)
    lane = Rect(x=lane_x, y=0, w=lane_w, d=D * PATH_END_FRACTION)

    closet = fr.rect_fwd(room.closet) if room.closet else None
    front, front_dir = _closet_front(closet, W, D) if closet else (None, "+y")
    obstacles = [r for r in (closet, front) if r]

    left_w, right_w = lane.x, W - lane.x2
    side: Literal["left", "right"] = "right" if right_w >= left_w else "left"
    right = side == "right"
    zone_w = right_w if right else left_w
    bed_wall_x, other_wall_x = (W, 0.0) if right else (0.0, W)
    bed_inner_x = lane.x2 if right else lane.x  # inner edge of the bed's zone
    below = D - lane.y2
    slots: dict[Role, SlotPlan] = {}

    # bed: far corner on the wide side, head at the bottom wall, long side along the side wall
    reg = _avoid(
        Rect(x=lane.x2 if right else 0, y=lane.y2, w=zone_w, d=below),
        1 if right else -1,
        1,
        obstacles,
    )
    slots["bed"] = SlotPlan(
        "bed", reg, "y", (bed_wall_x, D), -1, -1 if right else 1, reg.d, reg.w
    )

    # desk: bottom corner of the other side, long side along that wall, chair pulled out in front
    # (chair + 18 in behind it may overlap the lane, which is empty space)
    chair_across = CHAIR_ASSUMED[1]
    span = abs(bed_inner_x - other_wall_x) - chair_across - CHAIR_BACK
    span = max(span, 0.0)
    desk_x = 0.0 if other_wall_x == 0 else W - span
    reg = _avoid(
        Rect(x=desk_x, y=lane.y2, w=span, d=below),
        -1 if other_wall_x == 0 else 1,
        1,
        obstacles,
    )
    slots["desk"] = SlotPlan(
        "desk",
        reg,
        "y",
        (other_wall_x, D),
        -1,
        1 if other_wall_x == 0 else -1,
        reg.d,
        reg.w,
    )
    chair_region = Rect(x=0, y=0, w=0, d=0)
    slots["desk_chair"] = SlotPlan(
        "desk_chair",
        chair_region,
        "x",
        (0, 0),
        1,
        1,
        CHAIR_ASSUMED[0],
        CHAIR_ASSUMED[1],
    )

    # dresser: top wall on the bed's side of the lane, front clearance stays above the bed zone
    reg = _avoid(
        Rect(
            x=lane.x2 if right else 0,
            y=0,
            w=zone_w,
            d=max(lane.y2 - FRONT_CLEARANCE, 0),
        ),
        1 if right else -1,
        -1,
        obstacles,
    )
    slots["dresser"] = SlotPlan(
        "dresser", reg, "x", (bed_wall_x, 0), -1 if right else 1, 1, reg.w, reg.d
    )

    # nightstand: bottom wall, next to the bed's open side at the head
    reg = _avoid(
        Rect(x=lane.x, y=lane.y2, w=lane.w, d=below), 1 if right else -1, 1, obstacles
    )
    slots["nightstand"] = SlotPlan(
        "nightstand", reg, "x", (bed_inner_x, D), -1 if right else 1, -1, reg.w, reg.d
    )

    # a desk chair only makes sense with a desk
    if not slots["desk"].fits:
        slots["desk_chair"].max_along = slots["desk_chair"].max_across = 0.0

    return Plan(fr, W, D, lane, closet, front, front_dir, side, slots)


NO_FIT = {
    "bed": "no bed fits under these rules",
    "desk": "no desk fits under these rules",
    "desk_chair": "no desk chair fits (there is no desk)",
    "dresser": "no dresser fits under these rules",
    "nightstand": "no nightstand fits under these rules",
}


def public_slots(room: Room, plan: Plan | None = None) -> list[Slot]:
    plan = plan or plan_room(room)
    out: list[Slot] = []
    for role, sp in plan.slots.items():
        region = plan.frame.rect_back(sp.region) if sp.region.area > 0 else sp.region
        out.append(
            Slot(
                id=role,
                role=role,
                region=region,
                max_footprint=(round(sp.max_along, 2), round(sp.max_across, 2)),
                fits=sp.fits,
                assumed_footprint=role == "desk_chair",
                note=None if sp.fits else NO_FIT[role],
            )
        )
    return out
