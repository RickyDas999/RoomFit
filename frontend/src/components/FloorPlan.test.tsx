import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { FloorPlan } from './FloorPlan'
import { BROKEN_CHAIR_PLAN, makePlan, zone } from '../testFixtures'
import { SAMPLE_FORM, toRoom } from '../room'

afterEach(cleanup)
const room = toRoom(SAMPLE_FORM)

describe('FloorPlan', () => {
  it('is drawn to scale: one SVG unit per inch, plus a margin', () => {
    render(<FloorPlan room={room} plan={makePlan()} />)
    const svg = screen.getByTestId('floorplan')
    const [x, y, w, h] = svg.getAttribute('viewBox')!.split(' ').map(Number)
    expect([w, h]).toEqual([144 + 2 * 14, 192 + 2 * 14])
    expect([x, y]).toEqual([-14, -14])
  })

  it('draws each placed piece at its own coordinates and size', () => {
    render(<FloorPlan room={room} plan={makePlan()} />)
    const piece = screen.getByTestId('piece-bed')
    expect(within(piece).getByText('Bed, 40 x 80 in')).toBeInTheDocument()
    const bed = piece.querySelector('rect')!
    expect(bed.getAttribute('x')).toBe('104')
    expect(bed.getAttribute('y')).toBe('112')
    expect(bed.getAttribute('width')).toBe('40')
    expect(bed.getAttribute('height')).toBe('80')
  })

  it('marks the chair as an assumed size', () => {
    render(<FloorPlan room={room} plan={makePlan()} />)
    expect(within(screen.getByTestId('piece-desk_chair')).getByText(/assumed size/)).toBeInTheDocument()
    expect(screen.getByTestId('piece-desk_chair').querySelector('rect')).toHaveClass('plan__piece--assumed')
  })

  it('draws the closet, the door swing and the window', () => {
    render(<FloorPlan room={room} plan={makePlan()} />)
    expect(screen.getByTestId('closet')).toHaveTextContent('Closet')
    expect(screen.getByTestId('door-swing').getAttribute('d')).toBe('M 88 0 A 32 32 0 0 1 56 32')
  })

  it('leaves out the closet when there is none', () => {
    render(<FloorPlan room={{ ...room, closet: null }} plan={makePlan()} />)
    expect(screen.queryByTestId('closet')).toBeNull()
  })

  it('shades clearance zones, red and labelled only when broken', () => {
    render(<FloorPlan room={room} plan={BROKEN_CHAIR_PLAN()} />)
    const ok = screen.getByTestId('zone-path_from_door')
    const bad = screen.getByTestId('zone-behind_desk_chair')
    expect(ok.dataset.broken).toBe('false')
    expect(ok.querySelector('rect')).not.toHaveClass('plan__zone--broken')
    expect(bad.dataset.broken).toBe('true')
    expect(bad.querySelector('rect')).toHaveClass('plan__zone--broken')
    expect(screen.getByTestId('zone-label-behind_desk_chair')).toHaveTextContent('6 in short')
    expect(screen.queryByTestId('zone-label-path_from_door')).toBeNull()
  })

  it('puts the "in short" label after the furniture so nothing can cover it', () => {
    const { container } = render(<FloorPlan room={room} plan={BROKEN_CHAIR_PLAN()} />)
    const kids = [...container.querySelector('svg')!.children]
    const label = kids.indexOf(screen.getByTestId('zone-label-behind_desk_chair'))
    const piece = kids.indexOf(screen.getByTestId('piece-bed'))
    expect(label).toBeGreaterThan(piece)
  })

  it('formats the inches short without float noise', () => {
    const plan = makePlan({ zones: [zone('bed_open_side', true, 0.1 + 0.2)] })
    render(<FloorPlan room={room} plan={plan} />)
    expect(screen.getByTestId('zone-label-bed_open_side')).toHaveTextContent('0.3 in short')
  })

  it('describes the plan for screen readers, including broken clearances', () => {
    render(<FloorPlan room={room} plan={BROKEN_CHAIR_PLAN()} />)
    const label = screen.getByRole('img').getAttribute('aria-label')!
    expect(label).toMatch(/144 by 192 inches/)
    expect(label).toMatch(/Placed: bed, desk, desk chair/)
    expect(label).toMatch(/Broken clearances: behind the desk chair/)
  })

  it('says all clearances are met, and when nothing is placed', () => {
    render(<FloorPlan room={room} plan={makePlan({ placed: {}, zones: [] })} />)
    expect(screen.getByRole('img').getAttribute('aria-label')).toMatch(/No furniture placed yet\. All clearances are met\./)
  })

  it('dims the plan while it is being re-checked', () => {
    const { container } = render(<FloorPlan room={room} plan={makePlan()} stale />)
    expect(container.querySelector('figure')).toHaveClass('plan--stale')
  })

  it('draws a plan for a room with the door on another wall', () => {
    const left = { ...room, width: 192, depth: 144, door: { wall: 'left' as const, offset: 56, width: 32, swing: 'in' as const } }
    render(<FloorPlan room={left} plan={makePlan({ zones: [] })} />)
    expect(screen.getByTestId('door-swing').getAttribute('d')).toBe('M 0 88 A 32 32 0 0 0 32 56')
  })
})
