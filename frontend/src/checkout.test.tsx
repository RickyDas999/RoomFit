import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import type { CartSession } from './api/types'
import { CheckoutPanel } from './components/CheckoutPanel'
import { formatMoney } from './format'
import { BIG_DESK, makePlan, makeRecommend } from './testFixtures'

const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } }))
const session = (over: Partial<CartSession> = {}): CartSession => ({
  shop: { id: 'gid://shopify/Shop/1', name: 'Shop A', domain: 'shop-a.example.com' },
  status: 'created',
  cart_id: 'gid://shopify/Cart/c1?key=k',
  currency: 'USD',
  lines: [{ title: 'Small desk', quantity: 1, amount: 4000 }],
  totals: [
    { type: 'subtotal', amount: 4000, display_text: 'Subtotal' },
    { type: 'total', amount: 4000, display_text: 'Total' },
  ],
  messages: [],
  continue_url: 'https://shop-a.example.com/cart/c/c1?key=k',
  error: null,
  ...over,
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('formatMoney', () => {
  it('turns cents into dollars, and survives an odd currency', () => {
    expect(formatMoney(5300, 'USD')).toBe('$53.00')
    expect(formatMoney(5300, null)).toBe('$53.00')
    expect(formatMoney(5300, 'not-a-currency')).toBe('53.00 not-a-currency')
  })
})

describe('CheckoutPanel', () => {
  const base = { canCreate: true, sessions: null, busy: 'idle' as const, error: null, onCreate: () => {}, onCancel: () => {} }

  it('says the purchase is disabled and never takes payment', () => {
    render(<CheckoutPanel {...base} />)
    expect(screen.getByRole('note')).toHaveTextContent('Prototype: purchase disabled.')
    expect(screen.getByRole('note')).toHaveTextContent('never takes payment')
  })

  it('makes carts only when something is chosen and none exist yet; cancel needs a real cart', () => {
    const { rerender } = render(<CheckoutPanel {...base} canCreate={false} />)
    expect(screen.getByRole('button', { name: 'Make a cart at each shop' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Cancel carts' })).toBeDisabled()
    rerender(<CheckoutPanel {...base} />)
    expect(screen.getByRole('button', { name: 'Make a cart at each shop' })).toBeEnabled()
    rerender(<CheckoutPanel {...base} sessions={[session()]} />)
    expect(screen.getByRole('button', { name: 'Make a cart at each shop' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Cancel carts' })).toBeEnabled()
    rerender(<CheckoutPanel {...base} sessions={[session({ status: 'error', cart_id: null })]} />)
    expect(screen.getByRole('button', { name: 'Cancel carts' })).toBeDisabled()
  })

  it('shows each merchant with its lines, total and a link to the merchant site', () => {
    render(<CheckoutPanel {...base} sessions={[session()]} />)
    const card = within(screen.getByTestId('cart-shop-a.example.com'))
    expect(card.getByText('Shop A')).toBeInTheDocument()
    expect(card.getByText('cart created')).toBeInTheDocument()
    expect(card.getByText(/1 × Small desk/)).toBeInTheDocument()
    expect(card.getByText('$40.00', { selector: 'strong' })).toBeInTheDocument()
    expect(card.getByRole('link', { name: 'Continue on merchant site' })).toHaveAttribute('href', 'https://shop-a.example.com/cart/c/c1?key=k')
  })

  it('never links to a page that is not https', () => {
    render(<CheckoutPanel {...base} sessions={[session({ continue_url: 'http://shop-a.example.com/c' })]} />)
    expect(screen.queryByRole('link', { name: 'Continue on merchant site' })).not.toBeInTheDocument()
  })

  it('shows a failed shop with its reason, and the shop messages', () => {
    render(<CheckoutPanel {...base} sessions={[session({ status: 'error', cart_id: null, lines: [], totals: [], continue_url: null, error: 'the shop answered HTTP 500' }), session({ shop: { id: 'x', name: 'Shop B', domain: 'shop-b.example.com' }, messages: [{ type: 'warning', code: 'quantity_adjusted', content: 'Only 1 left' }] })]} />)
    expect(screen.getByText('no cart')).toBeInTheDocument()
    expect(screen.getByText('the shop answered HTTP 500')).toBeInTheDocument()
    expect(screen.getByText('Only 1 left')).toBeInTheDocument()
  })

  it('shows progress, an error, and an empty state', () => {
    const { rerender } = render(<CheckoutPanel {...base} busy="creating" />)
    expect(screen.getByRole('button', { name: 'Making carts…' })).toBeDisabled()
    rerender(<CheckoutPanel {...base} busy="cancelling" sessions={[session()]} />)
    expect(screen.getByRole('button', { name: 'Cancelling…' })).toBeDisabled()
    rerender(<CheckoutPanel {...base} error="Could not reach the Room Fit server." />)
    expect(screen.getByRole('alert')).toHaveTextContent('Could not reach')
    rerender(<CheckoutPanel {...base} sessions={[]} />)
    expect(screen.getByText('Nothing chosen yet.')).toBeInTheDocument()
  })

  it('reports the two button clicks', () => {
    const onCreate = vi.fn()
    const onCancel = vi.fn()
    const { rerender } = render(<CheckoutPanel {...base} onCreate={onCreate} onCancel={onCancel} />)
    fireEvent.click(screen.getByRole('button', { name: 'Make a cart at each shop' }))
    rerender(<CheckoutPanel {...base} onCreate={onCreate} onCancel={onCancel} sessions={[session()]} />)
    fireEvent.click(screen.getByRole('button', { name: 'Cancel carts' }))
    expect(onCreate).toHaveBeenCalledTimes(1)
    expect(onCancel).toHaveBeenCalledTimes(1)
  })
})

interface Api {
  checkout?: (body: { layout: unknown[] }) => Promise<Response>
  cancel?: (body: { carts: { domain: string; cart_id: string }[] }) => Promise<Response>
}
function mockApi(api: Api = {}) {
  const f = vi.fn((url: string, init: RequestInit) => {
    const body = JSON.parse(String(init.body))
    if (url === '/api/evaluate') return json(makePlan())
    if (url === '/api/recommend') return json(makeRecommend())
    if (url === '/api/checkout') return (api.checkout ?? (() => json({ sessions: [session()], notice: 'Prototype: purchase disabled' })))(body)
    if (url === '/api/checkout/cancel') return (api.cancel ?? (() => json({ cancelled: 1, failed: 0 })))(body)
    return Promise.reject(new Error(`unexpected ${url}`))
  })
  vi.stubGlobal('fetch', f)
  return f
}
const to = (f: ReturnType<typeof mockApi>, url: string) => f.mock.calls.filter((c) => c[0] === url).map((c) => JSON.parse(String(c[1].body)))
const search = async () => {
  await screen.findByTestId('floorplan')
  fireEvent.click(screen.getByRole('button', { name: 'Find furniture that fits' }))
  await screen.findByText('Twin XL bed')
}
const makeCart = async () => {
  fireEvent.click(screen.getByRole('button', { name: 'Make a cart at each shop' }))
  await screen.findByTestId('cart-shop-a.example.com')
}

describe('carts in the app', () => {
  beforeEach(() => vi.unstubAllGlobals())

  it('is not offered before anything is chosen', async () => {
    mockApi()
    render(<App />)
    await screen.findByTestId('floorplan')
    expect(screen.getByRole('button', { name: 'Make a cart at each shop' })).toBeDisabled()
  })

  it('sends the chosen products and shows the carts', async () => {
    const f = mockApi()
    render(<App />)
    await search()
    await makeCart()
    const [body] = to(f, '/api/checkout')
    expect(body.layout.map((i: { slot_id: string }) => i.slot_id)).toEqual(['bed', 'desk', 'desk_chair'])
    expect(screen.getByText('Total:', { exact: false })).toBeInTheDocument()
  })

  it('cancels with the cart ids when the button is pressed, and clears the panel', async () => {
    const f = mockApi()
    render(<App />)
    await search()
    await makeCart()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel carts' }))
    await waitFor(() => expect(screen.queryByTestId('cart-shop-a.example.com')).not.toBeInTheDocument())
    expect(to(f, '/api/checkout/cancel')).toEqual([{ carts: [{ domain: 'shop-a.example.com', cart_id: 'gid://shopify/Cart/c1?key=k' }] }])
  })

  it('cancels automatically when the room changes', async () => {
    const f = mockApi()
    render(<App />)
    await search()
    await makeCart()
    fireEvent.change(screen.getByLabelText('Width (in)'), { target: { value: '150' } })
    await waitFor(() => expect(to(f, '/api/checkout/cancel')).toHaveLength(1))
    expect(screen.queryByTestId('cart-shop-a.example.com')).not.toBeInTheDocument()
  })

  it('cancels automatically when a swap changes what would be bought', async () => {
    const f = mockApi()
    render(<App />)
    await search()
    await makeCart()
    fireEvent.click(within(screen.getByTestId('slot-desk')).getByRole('button', { name: /Swap/ }))
    fireEvent.click(await screen.findByRole('button', { name: new RegExp(`Use ${BIG_DESK.title}`) }))
    await waitFor(() => expect(to(f, '/api/checkout/cancel')).toHaveLength(1))
    expect(screen.queryByTestId('cart-shop-a.example.com')).not.toBeInTheDocument()
  })

  it('does not call cancel when no cart was made', async () => {
    const f = mockApi()
    render(<App />)
    await search()
    fireEvent.change(screen.getByLabelText('Width (in)'), { target: { value: '150' } })
    await new Promise((r) => setTimeout(r, 50))
    expect(to(f, '/api/checkout/cancel')).toHaveLength(0)
  })

  it('does not try to cancel a cart that failed to be made', async () => {
    const f = mockApi({ checkout: () => json({ sessions: [session({ status: 'error', cart_id: null, error: 'the shop answered HTTP 500' })], notice: 'x' }) })
    render(<App />)
    await search()
    fireEvent.click(screen.getByRole('button', { name: 'Make a cart at each shop' }))
    await screen.findByText('the shop answered HTTP 500')
    fireEvent.change(screen.getByLabelText('Width (in)'), { target: { value: '150' } })
    await new Promise((r) => setTimeout(r, 50))
    expect(to(f, '/api/checkout/cancel')).toHaveLength(0)
  })

  it('cancels carts that arrive after the room already changed', async () => {
    let release!: (r: Response) => void
    const f = mockApi({ checkout: () => new Promise<Response>((res) => (release = res)) })
    render(<App />)
    await search()
    fireEvent.click(screen.getByRole('button', { name: 'Make a cart at each shop' }))
    fireEvent.change(screen.getByLabelText('Width (in)'), { target: { value: '150' } })
    release(new Response(JSON.stringify({ sessions: [session()], notice: 'x' }), { status: 200, headers: { 'content-type': 'application/json' } }))
    await waitFor(() => expect(to(f, '/api/checkout/cancel')).toHaveLength(1))
    expect(screen.queryByTestId('cart-shop-a.example.com')).not.toBeInTheDocument()
  })

  it('shows an error and keeps the button usable when the server is unreachable', async () => {
    mockApi({ checkout: () => Promise.reject(new Error('down')) })
    render(<App />)
    await search()
    fireEvent.click(screen.getByRole('button', { name: 'Make a cart at each shop' }))
    expect(await screen.findByText(/Could not reach|Something went wrong/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Make a cart at each shop' })).toBeEnabled()
  })

  it('tells the user when a cart could not be cancelled', async () => {
    mockApi({ cancel: () => json({ cancelled: 0, failed: 1 }) })
    render(<App />)
    await search()
    await makeCart()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel carts' }))
    expect(await screen.findByText(/1 cart\(s\) could not be cancelled/)).toBeInTheDocument()
  })

  it('sends a beacon to cancel the carts when the page is closed', async () => {
    mockApi()
    const beacon = vi.fn(() => true)
    vi.stubGlobal('navigator', { ...navigator, sendBeacon: beacon })
    render(<App />)
    await search()
    window.dispatchEvent(new Event('pagehide'))
    expect(beacon).not.toHaveBeenCalled() // nothing to cancel yet
    await makeCart()
    window.dispatchEvent(new Event('pagehide'))
    expect(beacon).toHaveBeenCalledTimes(1)
    const [url, blob] = beacon.mock.calls[0] as unknown as [string, Blob]
    expect(url).toBe('/api/checkout/cancel')
    expect(JSON.parse(await blob.text())).toEqual({ carts: [{ domain: 'shop-a.example.com', cart_id: 'gid://shopify/Cart/c1?key=k' }] })
  })
})
