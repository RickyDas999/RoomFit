import type { Room, Wall } from './api/types'

export interface Pt {
  x: number
  y: number
}

/** Where a wall starts, which way it runs, and which way is into the room. */
function wallFrame(room: Room, wall: Wall): { p0: Pt; a: Pt; n: Pt } {
  switch (wall) {
    case 'top':
      return { p0: { x: 0, y: 0 }, a: { x: 1, y: 0 }, n: { x: 0, y: 1 } }
    case 'bottom':
      return { p0: { x: 0, y: room.depth }, a: { x: 1, y: 0 }, n: { x: 0, y: -1 } }
    case 'left':
      return { p0: { x: 0, y: 0 }, a: { x: 0, y: 1 }, n: { x: 1, y: 0 } }
    case 'right':
      return { p0: { x: room.width, y: 0 }, a: { x: 0, y: 1 }, n: { x: -1, y: 0 } }
  }
}

const at = (p: Pt, v: Pt, t: number): Pt => ({ x: p.x + v.x * t, y: p.y + v.y * t })

export interface DoorGeometry {
  /** The two ends of the opening in the wall. */
  start: Pt
  end: Pt
  /** The door leaf when open 90 degrees, hinged at `start`. */
  leafEnd: Pt
  /** SVG path for the swing arc (from `end` to `leafEnd`, around `start`). */
  arc: string
}

/** Door opening, open leaf and swing arc. The leaf is hinged at the door's start. */
export function doorGeometry(room: Room): DoorGeometry {
  const { wall, offset, width, swing } = room.door
  const { p0, a, n } = wallFrame(room, wall)
  const dir = swing === 'out' ? { x: -n.x, y: -n.y } : n
  const start = at(p0, a, offset)
  const end = at(p0, a, offset + width)
  const leafEnd = at(start, dir, width)
  const cross = a.x * dir.y - a.y * dir.x // + means the arc runs clockwise on screen
  const sweep = cross > 0 ? 1 : 0
  return {
    start,
    end,
    leafEnd,
    arc: `M ${end.x} ${end.y} A ${width} ${width} 0 0 ${sweep} ${leafEnd.x} ${leafEnd.y}`,
  }
}

/** Window drawn as two thin lines along the wall. */
export function windowLines(room: Room): [Pt, Pt][] {
  const w = room.window
  if (!w) return []
  const { p0, a, n } = wallFrame(room, w.wall)
  const s = at(p0, a, w.offset)
  const e = at(p0, a, w.offset + w.width)
  const lines: [Pt, Pt][] = []
  for (const shift of [0.75, 2.25]) {
    lines.push([at(s, n, shift), at(e, n, shift)])
  }
  return lines
}
