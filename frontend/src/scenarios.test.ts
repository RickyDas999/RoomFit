import { describe, expect, it } from 'vitest'
import { SAMPLE_FORM, toRoom, validate } from './room'
import { SCENARIOS, matchScenario } from './scenarios'

describe('scenarios', () => {
  it('has the seven examples, the first being the sample room', () => {
    expect(SCENARIOS.map((s) => s.id)).toEqual(['starter', 'narrow', 'corner-door', 'small', 'wfh', 'studio', 'studio-no-desk'])
    expect(SCENARIOS[0].form).toEqual(SAMPLE_FORM)
  })

  it.each(SCENARIOS)('$label is a valid room the API accepts', ({ form }) => {
    expect(validate(form)).toEqual([])
    const room = toRoom(form)
    expect(room.door.offset + room.door.width).toBeLessThanOrEqual(form.doorWall === 'top' || form.doorWall === 'bottom' ? form.width : form.depth)
  })

  it('differ from each other, so each one shows something new', () => {
    const keys = SCENARIOS.map((s) => JSON.stringify(s.form))
    expect(new Set(keys).size).toBe(SCENARIOS.length)
  })

  it('prefills the needs: no desk for the small room and the desk-less studio, all three otherwise', () => {
    const needs = Object.fromEntries(SCENARIOS.map((s) => [s.id, s.form.needs]))
    expect(needs.small).toEqual(['nightstand', 'dresser'])
    expect(needs['studio-no-desk']).toEqual(['nightstand', 'dresser'])
    expect(needs.wfh).toContain('desk')
  })

  it('matches a form to its preset regardless of needs order, and a changed form to none', () => {
    const small = SCENARIOS.find((x) => x.id === 'small')!
    expect(matchScenario({ ...small.form, needs: ['dresser', 'nightstand'] })?.id).toBe('small')
    expect(matchScenario({ ...small.form, width: 121 })).toBeUndefined()
    expect(matchScenario({ ...small.form, bedSize: 'king' })).toBeUndefined()
  })

  it('has a narrow bedroom (10 x 16 ft, no closet) for the clearance moment, right after the sample room', () => {
    expect(SCENARIOS[1].id).toBe('narrow')
    expect(SCENARIOS[1].form).toMatchObject({ width: 124, depth: 192, closet: false, needs: ['nightstand', 'dresser', 'desk'], bedSize: 'auto' })
  })
})
