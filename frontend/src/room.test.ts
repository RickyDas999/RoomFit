import { describe, expect, it } from 'vitest'
import { SAMPLE_FORM, toRoom, validate, wallLength, type RoomForm } from './room'

const form = (over: Partial<RoomForm> = {}): RoomForm => ({ ...SAMPLE_FORM, ...over })

describe('toRoom', () => {
  it('turns the sample form into the API room (inches, 32 in door, 48 in window)', () => {
    expect(toRoom(SAMPLE_FORM)).toEqual({
      width: 144,
      depth: 192,
      door: { wall: 'top', offset: 56, width: 32, swing: 'in' },
      window: { wall: 'bottom', offset: 48, width: 48 },
      closet: { x: 0, y: 0, w: 48, d: 24 },
      needs: ['nightstand', 'dresser', 'desk'],
    })
  })

  it.each([
    ['top', { x: 0, y: 0, w: 48, d: 24 }],
    ['bottom', { x: 0, y: 168, w: 48, d: 24 }],
    ['left', { x: 0, y: 0, w: 24, d: 48 }],
    ['right', { x: 120, y: 0, w: 24, d: 48 }],
  ] as const)('puts the closet in the corner at the start of the %s door wall', (wall, rect) => {
    expect(toRoom(form({ doorWall: wall, windowWall: wall === 'top' ? 'bottom' : 'top' })).closet).toEqual(rect)
  })

  it('sends no closet when it is switched off', () => {
    expect(toRoom(form({ closet: false })).closet).toBeNull()
  })
})

describe('validate', () => {
  it('accepts the sample room', () => {
    expect(validate(SAMPLE_FORM)).toEqual([])
  })

  it('knows wall lengths', () => {
    expect(wallLength(SAMPLE_FORM, 'top')).toBe(144)
    expect(wallLength(SAMPLE_FORM, 'left')).toBe(192)
  })

  it('asks for every number', () => {
    expect(validate(form({ width: Number.NaN }))).toEqual(['Fill in every number.'])
    expect(validate(form({ doorOffset: Number.NaN }))).toEqual(['Fill in every number.'])
  })

  it('rejects a door that runs off its wall', () => {
    expect(validate(form({ doorOffset: 113 }))[0]).toMatch(/32 in door does not fit on the top wall/)
    expect(validate(form({ doorOffset: 112 }))).toEqual([]) // 112 + 32 = 144: exactly fits
    expect(validate(form({ doorOffset: -1 }))[0]).toMatch(/door/)
  })

  it('checks the door against the length of the wall it is on', () => {
    expect(validate(form({ doorWall: 'left', doorOffset: 160, windowWall: 'right' }))).toEqual([])
    expect(validate(form({ doorWall: 'left', doorOffset: 161, windowWall: 'right' }))[0]).toMatch(/left wall/)
  })

  it('rejects a window that runs off its wall', () => {
    expect(validate(form({ windowOffset: 97 }))[0]).toMatch(/48 in window does not fit on the bottom wall/)
    expect(validate(form({ windowOffset: 96 }))).toEqual([])
  })

  it('rejects a closet that does not fit the room', () => {
    const narrow = { width: 40, doorOffset: 4, windowWall: 'left', windowOffset: 0 } as const
    expect(validate(form(narrow))).toEqual([expect.stringMatching(/closet does not fit/)])
    expect(validate(form({ ...narrow, closet: false }))).toEqual([])
  })

  it('rejects empty rooms', () => {
    expect(validate(form({ width: 0 })).join(' ')).toMatch(/at least 1 inch/)
  })
})
