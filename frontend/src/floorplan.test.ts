import { describe, expect, it } from 'vitest'
import { doorGeometry, windowLines } from './floorplan'
import { SAMPLE_FORM, toRoom } from './room'
import type { Room, Wall } from './api/types'

const room = (wall: Wall, swing: 'in' | 'out' = 'in'): Room => ({
  width: 144,
  depth: 192,
  door: { wall, offset: 56, width: 32, swing },
  window: { wall: 'bottom', offset: 48, width: 48 },
  closet: null,
})

describe('doorGeometry', () => {
  it('draws the sample door on the top wall, hinged at its start, opening into the room', () => {
    const g = doorGeometry(toRoom(SAMPLE_FORM))
    expect(g.start).toEqual({ x: 56, y: 0 })
    expect(g.end).toEqual({ x: 88, y: 0 })
    expect(g.leafEnd).toEqual({ x: 56, y: 32 })
    expect(g.arc).toBe('M 88 0 A 32 32 0 0 1 56 32')
  })

  it.each([
    ['top', { x: 56, y: 0 }, { x: 88, y: 0 }, { x: 56, y: 32 }, 1],
    ['bottom', { x: 56, y: 192 }, { x: 88, y: 192 }, { x: 56, y: 160 }, 0],
    ['left', { x: 0, y: 56 }, { x: 0, y: 88 }, { x: 32, y: 56 }, 0],
    ['right', { x: 144, y: 56 }, { x: 144, y: 88 }, { x: 112, y: 56 }, 1],
  ] as const)('%s wall: opening, leaf and arc direction', (wall, start, end, leafEnd, sweep) => {
    const g = doorGeometry(room(wall))
    expect(g.start).toEqual(start)
    expect(g.end).toEqual(end)
    expect(g.leafEnd).toEqual(leafEnd)
    expect(g.arc).toBe(`M ${end.x} ${end.y} A 32 32 0 0 ${sweep} ${leafEnd.x} ${leafEnd.y}`)
  })

  it('swings outside the room when the door opens out', () => {
    const g = doorGeometry(room('top', 'out'))
    expect(g.leafEnd).toEqual({ x: 56, y: -32 })
  })

  it('the leaf is as long as the door is wide, so the arc is a true quarter circle', () => {
    for (const wall of ['top', 'bottom', 'left', 'right'] as const) {
      const g = doorGeometry(room(wall))
      expect(Math.hypot(g.leafEnd.x - g.start.x, g.leafEnd.y - g.start.y)).toBe(32)
    }
  })
})

describe('windowLines', () => {
  it('draws two thin lines along the window wall, just inside it', () => {
    const lines = windowLines(room('top'))
    expect(lines).toHaveLength(2)
    expect(lines[0][0]).toEqual({ x: 48, y: 192 - 0.75 })
    expect(lines[0][1]).toEqual({ x: 96, y: 192 - 0.75 })
  })

  it('draws nothing without a window', () => {
    expect(windowLines({ ...room('top'), window: null })).toEqual([])
  })
})
