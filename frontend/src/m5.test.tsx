import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { DataGap, SlotCard } from './components/SlotCard'
import { dataGapText, reasonText } from './format'
import { cand, makeProduct, makeSlots } from './testFixtures'
import type { LayoutItem, SearchStats } from './api/types'

afterEach(cleanup)

const deskSlot = makeSlots().find((s) => s.role === 'desk')!
const base = { slot: deskSlot, candidates: [], busy: false, onSwap: () => {} }
const item = (product = makeProduct('d')): LayoutItem => ({ slot_id: 'desk', product, footprint_basis: 'parsed' })
const inferred = makeProduct('inf', { title: 'Guessed desk', dimension_confidence: 'inferred', dimension_source: '48 x 24 x 30 in' })
const stats = (over: Partial<SearchStats> = {}): SearchStats => ({ found: 25, with_dimensions: 9, fit_slot: 5, stated: 6, inferred: 3, ambiguous: 4, missing: 12, ...over })

describe('confidence in the product card', () => {
  it('a stated size is badged "stated" and has no warning', () => {
    render(<SlotCard {...base} item={item()} />)
    expect(screen.getByText('stated')).toBeInTheDocument()
    expect(screen.queryByText('inferred')).not.toBeInTheDocument()
    expect(screen.getByText(/from the listing/)).toBeInTheDocument()
  })

  it('an inferred size gets a warning badge and says Shopify guessed it', () => {
    render(<SlotCard {...base} item={item(inferred)} />)
    expect(screen.getByText('inferred')).toBeInTheDocument()
    expect(screen.getByText(/guessed by Shopify from the product specs, so it may be wrong: “48 x 24 x 30 in”/)).toBeInTheDocument()
    expect(screen.queryByText(/from the listing/)).not.toBeInTheDocument()
  })

  it('the swap list marks inferred sizes too', () => {
    render(<SlotCard {...base} item={item()} candidates={[cand(makeProduct('a')), cand(inferred)]} />)
    fireEvent.click(screen.getByRole('button', { name: /Swap/ }))
    const row = screen.getByText('Guessed desk').closest('li')!
    expect(within(row).getByText('inferred')).toBeInTheDocument()
    expect(within(screen.getByText('Item a').closest('li')!).queryByText('inferred')).not.toBeInTheDocument()
  })

  it('a bed whose size does not match its name says so instead of a size', () => {
    const bad = makeProduct('q', { title: 'Queen bed', dimensions: null, dimension_status: 'ambiguous', dimension_reason: 'size_mismatch', dimension_confidence: 'ambiguous' })
    render(<SlotCard {...base} item={item(bad)} />)
    expect(screen.getByText('size unclear')).toBeInTheDocument()
    expect(screen.getByText('the listed size is smaller than the bed size in its name')).toBeInTheDocument()
  })
})

describe('a badge for every confidence class, in the card and in the swap list', () => {
  const classes = [
    ['stated', makeProduct('s1', { title: 'Stated desk' }), 'stated'],
    ['inferred', makeProduct('i1', { title: 'Guessed desk', dimension_confidence: 'inferred' }), 'inferred'],
    ['ambiguous', makeProduct('a1', { title: 'Unclear desk', dimensions: null, dimension_status: 'ambiguous', dimension_reason: 'multiple_sizes', dimension_confidence: 'ambiguous' }), 'size unclear'],
    ['missing', makeProduct('m1', { title: 'Blank desk', dimensions: null, dimension_status: 'missing', dimension_reason: 'no_dimensions', dimension_confidence: 'missing' }), 'dimensions missing'],
  ] as const

  it.each(classes)('the card shows the %s badge', (_name, product, text) => {
    render(<SlotCard {...base} item={item(product)} />)
    expect(screen.getByText(text, { selector: '.badge' })).toBeInTheDocument()
  })

  it('the swap list shows one badge per listing, matching its class', () => {
    render(<SlotCard {...base} item={item()} candidates={classes.map(([, p]) => cand(p, false))} />)
    fireEvent.click(screen.getByRole('button', { name: /Swap/ }))
    for (const [, product, text] of classes) {
      const row = screen.getByText(product.title).closest('li')!
      expect(within(row).getByText(text, { selector: '.badge' })).toBeInTheDocument()
    }
  })
})

describe('odd combinations never read as a trusted size', () => {
  it.each([
    ['parsed but confidence ambiguous', makeProduct('o1', { dimension_confidence: 'ambiguous' })],
    ['parsed but confidence missing', makeProduct('o2', { dimension_confidence: 'missing' })],
    ['status ambiguous with a stated confidence', makeProduct('o3', { dimensions: null, dimension_status: 'ambiguous', dimension_confidence: 'stated' })],
  ])('%s says "size unclear"', (_n, product) => {
    render(<SlotCard {...base} item={item(product)} />)
    expect(screen.getByText('size unclear', { selector: '.badge' })).toBeInTheDocument()
    expect(screen.queryByText('stated')).not.toBeInTheDocument()
  })

  it('a placed-looking size with no dimensions at all is "dimensions missing", never "inferred"', () => {
    render(<SlotCard {...base} item={item(makeProduct('o4', { dimensions: null, dimension_status: 'missing', dimension_confidence: 'inferred' }))} />)
    expect(screen.getByText('dimensions missing', { selector: '.badge' })).toBeInTheDocument()
    expect(screen.queryByText('inferred')).not.toBeInTheDocument()
  })
})

describe('rotation note', () => {
  it('says a piece is turned 90 degrees, only when it is', () => {
    const { rerender } = render(<SlotCard {...base} item={item()} rotated />)
    expect(screen.getByText(/Turned 90°/)).toBeInTheDocument()
    rerender(<SlotCard {...base} item={item()} rotated={false} />)
    expect(screen.queryByText(/Turned 90°/)).not.toBeInTheDocument()
  })

  it('does not mention a turn for an empty slot', () => {
    render(<SlotCard {...base} rotated />)
    expect(screen.queryByText(/Turned 90°/)).not.toBeInTheDocument()
  })
})

describe('data gap', () => {
  it('says how many listings had usable dimensions, per slot', () => {
    render(<SlotCard {...base} item={item()} gap={stats()} />)
    expect(screen.getByText('Of 25 desks Shopify returned, 9 list usable dimensions (6 stated, 3 inferred).')).toBeInTheDocument()
  })

  it('leaves out the stated/inferred split when nothing was inferred, and never shows it for the chair or an empty search', () => {
    expect(dataGapText('desk', stats({ inferred: 0, stated: 9 }))).toBe('Of 25 desks Shopify returned, 9 list usable dimensions.')
    render(<SlotCard {...base} slot={makeSlots().find((s) => s.role === 'desk_chair')!} gap={stats()} />)
    expect(screen.queryByText(/Shopify returned/)).not.toBeInTheDocument()
    cleanup()
    render(<SlotCard {...base} item={item()} gap={stats({ found: 0, with_dimensions: 0 })} />)
    expect(screen.queryByText(/Shopify returned/)).not.toBeInTheDocument()
  })

  it('uses plain words for every searchable role and falls back for odd ones', () => {
    for (const [role, word] of [['bed', 'beds'], ['dresser', 'dressers'], ['nightstand', 'nightstands'], ['constructor', 'products']] as const) {
      expect(dataGapText(role, stats())).toContain(`25 ${word} Shopify`)
    }
  })

  it('sums the whole search, leaving out the chair (its size is assumed)', () => {
    render(<DataGap searched={{ desk: stats(), bed: stats({ found: 10, with_dimensions: 3 }), desk_chair: stats({ found: 99, with_dimensions: 0 }) }} />)
    expect(screen.getByTestId('data-gap')).toHaveTextContent('Shopify returned 35 listings. Only 12 list usable dimensions.')
  })

  it('shows nothing when nothing was searched', () => {
    render(<DataGap searched={{}} />)
    expect(screen.queryByTestId('data-gap')).not.toBeInTheDocument()
  })
})

describe('reason text', () => {
  it('has words for the size check', () => {
    expect(reasonText('size_mismatch')).toMatch(/smaller than the bed size/)
  })
})
