import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { STORE_NAME, StoreFooter, StoreHeader } from './components/StoreChrome'
import { makePlan } from './testFixtures'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const FOCUSABLE = 'a, button, input, select, textarea, [tabindex]'

describe('the store around the Room Planner is for show only', () => {
  it('has a placeholder store name, a nav with the Room Planner as the current page, and no way to interact', () => {
    const { container } = render(
      <>
        <StoreHeader />
        <StoreFooter />
      </>,
    )
    expect(STORE_NAME).toBe('Northfield Home')
    expect(container.querySelector('.store-header__logo')).toHaveTextContent('Northfield Home')
    expect(container.querySelector('.store-header__nav .is-current')).toHaveTextContent('Room Planner')
    // nothing in the store chrome can be focused, clicked or followed
    expect(container.querySelectorAll(FOCUSABLE)).toHaveLength(0)
  })

  it('is hidden from screen readers, so only the Room Planner is announced', () => {
    const { container } = render(
      <>
        <StoreHeader />
        <StoreFooter />
      </>,
    )
    expect(container.querySelector('.announce')).toHaveAttribute('aria-hidden', 'true')
    expect(container.querySelector('.store-header')).toHaveAttribute('aria-hidden', 'true') // no second banner landmark
    expect(container.querySelector('.store-header__nav')).toHaveAttribute('aria-hidden', 'true')
    expect(container.querySelector('.store-header__tools')).toHaveAttribute('aria-hidden', 'true')
    expect(container.querySelector('.store-footer')).toHaveAttribute('aria-hidden', 'true')
  })

  it('says on the page that this is the Room Planner and that the store around it is a placeholder', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(new Response(JSON.stringify(makePlan()), { status: 200, headers: { 'content-type': 'application/json' } }))),
    )
    const { container } = render(<App />)
    expect(screen.getByRole('heading', { level: 1, name: 'Room Planner' })).toBeInTheDocument()
    expect(screen.getByText(/real furniture that fits and leaves space to walk around it/)).toBeInTheDocument()
    expect(screen.getByText(/prototype of the Room Planner inside a merchant’s online store/)).toBeInTheDocument()
    // the planner's own controls are the only things you can use on the page
    const store = container.querySelectorAll('.announce, .store-header, .store-footer')
    store.forEach((el) => expect(el.querySelectorAll(FOCUSABLE)).toHaveLength(0))
    expect(await screen.findByTestId('floorplan')).toBeInTheDocument()
  })

  it('has no banner landmark of its own besides the hidden store header', () => {
    render(<App />)
    expect(screen.queryAllByRole('banner')).toHaveLength(0)
  })

  it('keeps the single page-level heading the Room Planner (the store name is not a heading)', () => {
    render(<App />)
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
  })
})
