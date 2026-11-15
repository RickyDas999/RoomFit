import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SlotCard } from './SlotCard'
import { BIG_DESK, NO_SIZE_DESK, SMALL_DESK, cand, makeProduct, makeSlots, missing } from '../testFixtures'
import type { LayoutItem } from '../api/types'

afterEach(cleanup)

const deskSlot = makeSlots().find((s) => s.role === 'desk')!
const chairSlot = makeSlots().find((s) => s.role === 'desk_chair')!
const item = (product = SMALL_DESK, basis: LayoutItem['footprint_basis'] = 'parsed'): LayoutItem => ({ slot_id: 'desk', product, footprint_basis: basis })

const base = { slot: deskSlot, candidates: [], busy: false, onSwap: () => {} }

describe('SlotCard product', () => {
  it('shows the title, shop, price and the size with the listing text it came from', () => {
    render(<SlotCard {...base} item={item()} />)
    expect(screen.getByText('Small desk')).toBeInTheDocument()
    expect(screen.getByText(/Test Shop/)).toBeInTheDocument()
    expect(screen.getByText('$40.00')).toBeInTheDocument()
    expect(screen.getByText('48 × 24 × 30 in')).toBeInTheDocument()
    expect(screen.getByText(/from the listing: “48" x 24" x 30"”/)).toBeInTheDocument()
  })

  it('leaves out the height when the listing has none', () => {
    render(<SlotCard {...base} item={item(makeProduct('x', { dimensions: { w: 48, d: 24, h: null } }))} />)
    expect(screen.getByText('48 × 24 in')).toBeInTheDocument()
  })

  it('shows a "dimensions missing" badge and why, instead of a size', () => {
    render(<SlotCard {...base} item={item(missing('m', 'multiple_sizes'))} />)
    expect(screen.getByText('dimensions missing')).toBeInTheDocument()
    expect(screen.getByText('several sizes listed')).toBeInTheDocument()
    expect(screen.queryByText(/ in$/)).toBeNull()
  })

  it('treats an unclear listing the same as a missing one', () => {
    const unclear = makeProduct('u', { dimensions: null, dimension_status: 'ambiguous', dimension_reason: 'shipping_size' })
    render(<SlotCard {...base} item={item(unclear)} />)
    expect(screen.getByText('dimensions missing')).toBeInTheDocument()
    expect(screen.getByText('only a shipping or box size')).toBeInTheDocument()
  })

  it('labels the chair size as assumed and says why', () => {
    render(<SlotCard {...base} slot={chairSlot} item={{ ...item(missing('c')), slot_id: 'desk_chair', footprint_basis: 'assumed' }} />)
    expect(screen.getByText('assumed 20 × 20 in')).toBeInTheDocument()
    expect(screen.queryByText('dimensions missing')).toBeNull()
  })

  it('links the title only for https product pages', () => {
    const { rerender } = render(<SlotCard {...base} item={item()} />)
    const link = screen.getByRole('link', { name: 'Small desk' })
    expect(link).toHaveAttribute('href', 'https://shop.example/products/desk-small')
    expect(link).toHaveAttribute('rel', 'noreferrer')
    rerender(<SlotCard {...base} item={item(makeProduct('h', { title: 'Plain http', url: 'http://shop.example/x' }))} />)
    expect(screen.queryByRole('link')).toBeNull()
    rerender(<SlotCard {...base} item={item(makeProduct('j', { title: 'Script url', url: 'javascript:alert(1)' }))} />)
    expect(screen.queryByRole('link')).toBeNull()
    expect(screen.getByText('Script url')).toBeInTheDocument()
  })
})

describe('SlotCard states', () => {
  it('says there is no space when the slot cannot hold anything', () => {
    render(<SlotCard {...base} slot={{ ...deskSlot, fits: false, note: 'no desk fits under these rules' }} />)
    expect(screen.getByText('no space')).toBeInTheDocument()
    expect(screen.getByText('no desk fits under these rules')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Swap/ })).toBeNull()
  })

  it('shows why nothing was chosen', () => {
    render(<SlotCard {...base} unplacedReason="no listing with usable dimensions" />)
    expect(screen.getByText('no listing with usable dimensions')).toBeInTheDocument()
  })

  it('shows a placeholder before any search', () => {
    render(<SlotCard {...base} />)
    expect(screen.getByText('Nothing chosen yet.')).toBeInTheDocument()
  })

  it('explains a chosen product that could not be placed', () => {
    render(<SlotCard {...base} item={item(NO_SIZE_DESK)} unplacedReason="dimensions missing" />)
    expect(screen.getAllByText(/dimensions missing/).length).toBeGreaterThan(1)
  })
})

describe('SlotCard swap', () => {
  const candidates = [cand(NO_SIZE_DESK, false), cand(SMALL_DESK), cand(BIG_DESK, false)]

  it('hides the list until asked, and is a proper disclosure button', () => {
    render(<SlotCard {...base} item={item()} candidates={candidates} />)
    const button = screen.getByRole('button', { name: 'Swap (3 found)' })
    expect(button).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('list')).toBeNull()
    fireEvent.click(button)
    expect(button).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getAllByRole('listitem')).toHaveLength(3)
    fireEvent.click(screen.getByRole('button', { name: 'Hide alternatives' }))
    expect(screen.queryByRole('list')).toBeNull()
  })

  it('shows every alternative, including ones that are too big or have no size', () => {
    render(<SlotCard {...base} item={item()} candidates={candidates} />)
    fireEvent.click(screen.getByRole('button', { name: /Swap/ }))
    const rows = screen.getAllByRole('listitem')
    expect(within(rows[0]).getByText('dimensions missing')).toBeInTheDocument()
    expect(within(rows[2]).getByText('72 × 72 × 30 in')).toBeInTheDocument()
    expect(within(rows[2]).getByText('bigger than the space')).toBeInTheDocument()
    expect(within(rows[1]).queryByText('bigger than the space')).toBeNull()
  })

  it('marks the current product as selected and does not let you pick it again', () => {
    render(<SlotCard {...base} item={item()} candidates={candidates} />)
    fireEvent.click(screen.getByRole('button', { name: /Swap/ }))
    const selected = screen.getByRole('button', { name: 'Small desk is selected' })
    expect(selected).toBeDisabled()
    expect(selected).toHaveTextContent('Selected')
  })

  it('swaps in the chosen product', () => {
    const onSwap = vi.fn()
    render(<SlotCard {...base} item={item()} candidates={candidates} onSwap={onSwap} />)
    fireEvent.click(screen.getByRole('button', { name: /Swap/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Use Big corner desk as the desk' }))
    expect(onSwap).toHaveBeenCalledTimes(1)
    expect(onSwap).toHaveBeenCalledWith(BIG_DESK)
  })

  it('can swap in a product with no size (it will show as unplaceable)', () => {
    const onSwap = vi.fn()
    render(<SlotCard {...base} item={item()} candidates={candidates} onSwap={onSwap} />)
    fireEvent.click(screen.getByRole('button', { name: /Swap/ }))
    fireEvent.click(screen.getByRole('button', { name: `Use ${NO_SIZE_DESK.title} as the desk` }))
    expect(onSwap).toHaveBeenCalledWith(NO_SIZE_DESK)
  })

  it('disables the buttons while a check is running', () => {
    render(<SlotCard {...base} item={item()} candidates={candidates} busy />)
    fireEvent.click(screen.getByRole('button', { name: /Swap/ }))
    for (const b of screen.getAllByRole('button', { name: /^Use / })) expect(b).toBeDisabled()
  })

  it('does not show sizes for chair alternatives, since the size is assumed', () => {
    render(
      <SlotCard
        {...base}
        slot={chairSlot}
        item={{ ...item(missing('c')), slot_id: 'desk_chair', footprint_basis: 'assumed' }}
        candidates={[cand(missing('c1')), cand(missing('c2'))]}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /Swap/ }))
    expect(screen.queryByText('dimensions missing')).toBeNull()
  })
})
