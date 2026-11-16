import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { DataGap, SlotCard } from './components/SlotCard'
import { dataGapText } from './format'
import { cand, makeProduct, makeSlots } from './testFixtures'
import type { LayoutItem, SearchStats } from './api/types'

afterEach(cleanup)

const deskSlot = makeSlots().find((s) => s.role === 'desk')!
const base = { slot: deskSlot, candidates: [], busy: false, onSwap: () => {} }
const item = (product = makeProduct('d')): LayoutItem => ({ slot_id: 'desk', product, footprint_basis: 'parsed' })
const inferred = makeProduct('inf', { title: 'Guessed desk', dimension_confidence: 'inferred', dimension_source: '48 x 24 x 30 in' })
const st = (over: Partial<SearchStats> = {}): SearchStats => ({ found: 25, with_dimensions: 9, fit_slot: 5, stated: 6, inferred: 3, ambiguous: 4, missing: 12, ...over })

describe('dataGapText edge cases', () => {
  it('handles undefined stated/inferred (old server) without NaN or undefined', () => {
    const t = dataGapText('desk', { found: 4, with_dimensions: 2 })
    expect(t).toBe('Of 4 desks Shopify returned, 2 list usable dimensions.')
    expect(dataGapText('desk', { found: 4, with_dimensions: 2, inferred: 1 })).toContain('(0 stated, 1 inferred)')
  })

  it.each(['constructor', 'toString', '__proto__', 'hasOwnProperty', ''])('role %j falls back to "products"', (role) => {
    expect(dataGapText(role, st())).toContain('25 products Shopify')
  })

  it('prints very large numbers as given and does not crash', () => {
    expect(dataGapText('bed', st({ found: 1e9, with_dimensions: 1e9 }))).toContain('1000000000 beds')
  })
})

describe('DataGap edge cases', () => {
  it('ignores undefined entries and the chair, and shows nothing if all found are 0', () => {
    render(<DataGap searched={{ desk: undefined, bed: st({ found: 0, with_dimensions: 0 }) }} />)
    expect(screen.queryByTestId('data-gap')).not.toBeInTheDocument()
  })

  it('does not choke on a role literally named constructor', () => {
    render(<DataGap searched={{ constructor: st({ found: 3, with_dimensions: 1 }) }} />)
    expect(screen.getByTestId('data-gap')).toHaveTextContent('Shopify returned 3 listings. Only 1 list usable dimensions.')
  })

  it('sums very large numbers', () => {
    render(<DataGap searched={{ desk: st({ found: 1e9, with_dimensions: 5e8 }), bed: st({ found: 1e9, with_dimensions: 5e8 }) }} />)
    expect(screen.getByTestId('data-gap')).toHaveTextContent('Shopify returned 2000000000 listings. Only 1000000000 list usable dimensions.')
  })
})

describe('SlotCard edge cases', () => {
  it('renders with gap whose optional fields are undefined', () => {
    render(<SlotCard {...base} item={item()} gap={{ found: 3, with_dimensions: 1, fit_slot: 1 } as SearchStats} />)
    expect(screen.getByText('Of 3 desks Shopify returned, 1 list usable dimensions.')).toBeInTheDocument()
  })

  it('shows rotation note and gap line together, and rotated undefined shows no note', () => {
    const { rerender } = render(<SlotCard {...base} item={item()} rotated gap={st()} />)
    expect(screen.getByText(/Turned 90°/)).toBeInTheDocument()
    expect(screen.getByText(/Of 25 desks/)).toBeInTheDocument()
    rerender(<SlotCard {...base} item={item()} rotated={undefined} />)
    expect(screen.queryByText(/Turned 90°/)).not.toBeInTheDocument()
  })

  it('an unfit slot shows no data gap for an empty slot', () => {
    render(<SlotCard {...base} gap={st()} />)
    expect(screen.queryByText(/Turned 90°/)).not.toBeInTheDocument()
  })

  it('inferred badge appears in the swap list for the currently selected inferred item', () => {
    render(<SlotCard {...base} item={item(inferred)} candidates={[cand(inferred), cand(makeProduct('b'))]} />)
    fireEvent.click(screen.getByRole('button', { name: /Swap/ }))
    const rows = screen.getAllByText('Guessed desk').map((e) => e.closest('li')).filter(Boolean)
    expect(rows.length).toBeGreaterThan(0)
    expect(within(rows[0]!).getByText('inferred')).toBeInTheDocument()
  })

  it('an inferred item with no source shows the badge but no hint text', () => {
    render(<SlotCard {...base} item={item(makeProduct('i2', { dimension_confidence: 'inferred', dimension_source: null }))} />)
    expect(screen.getByText('inferred')).toBeInTheDocument()
    expect(screen.queryByText(/guessed by Shopify/)).not.toBeInTheDocument()
  })

  it('an ambiguous or missing item never shows the inferred badge', () => {
    render(<SlotCard {...base} item={item(makeProduct('a', { dimension_confidence: 'ambiguous', dimensions: null, dimension_status: 'ambiguous' }))} />)
    expect(screen.queryByText('inferred')).not.toBeInTheDocument()
  })

  it('does not show the gap line for the chair even with rotated set', () => {
    const chair = makeSlots().find((s) => s.role === 'desk_chair')!
    render(<SlotCard {...base} slot={chair} item={{ slot_id: 'desk_chair', product: makeProduct('c'), footprint_basis: 'assumed' }} gap={st()} />)
    expect(screen.queryByText(/Shopify returned/)).not.toBeInTheDocument()
  })
})
