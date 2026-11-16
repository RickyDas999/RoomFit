import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { cancelCartsOnExit, cartRefs } from './api/client'
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
  totals: [{ type: 'total', amount: 4000, display_text: 'Total' }],
  messages: [],
  continue_url: 'https://shop-a.example.com/cart/c/c1?key=k',
  error: null,
  ...over,
})
const REF = { domain: 'shop-a.example.com', cart_id: 'gid://shopify/Cart/c1?key=k' }

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('formatMoney edge cases', () => {
  it.each([
    [0, '$0.00'],
    [-500, '-$5.00'],
    [1, '$0.01'],
    [100000000000, '$1,000,000,000.00'],
  ])('%s', (cents, text) => expect(formatMoney(cents, 'USD')).toBe(text))

  it('never throws on NaN, infinity, fractional cents or odd currencies', () => {
    for (const n of [NaN, Infinity, -Infinity, 50.5, 0.4, 1e21, Number.MAX_SAFE_INTEGER]) {
      expect(typeof formatMoney(n, 'USD')).toBe('string')
    }
    for (const c of ['', 'usd', 'US', 'XXXX', '💥', 'EUR', 'JPY', undefined, null]) {
      expect(typeof formatMoney(100, c)).toBe('string')
    }
    expect(formatMoney(NaN, 'USD')).toContain('NaN')
  })
  it('an empty currency string does not show a blank code', () => {
    expect(formatMoney(5300, '')).toMatch(/53\.00/)
  })
})

describe('CheckoutPanel edge cases', () => {
  const base = { canCreate: true, sessions: null, busy: 'idle' as const, error: null, onCreate: () => {}, onCancel: () => {} }
  const shopN = (i: number) => ({ id: `gid://shopify/Shop/${i}`, name: `Shop ${i}`, domain: `s${i}.example.com` })

  it('renders 50 sessions, each once', () => {
    const sessions = Array.from({ length: 50 }, (_, i) => session({ shop: shopN(i), cart_id: `gid://shopify/Cart/${i}` }))
    render(<CheckoutPanel {...base} sessions={sessions} />)
    expect(screen.getAllByRole('link', { name: 'Continue on merchant site' })).toHaveLength(50)
    expect(screen.getByTestId('cart-s49.example.com')).toBeInTheDocument()
  })

  it('two sessions with the same domain do not trigger a React duplicate-key warning', () => {
    const err = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(<CheckoutPanel {...base} sessions={[session(), session({ cart_id: 'gid://shopify/Cart/other' })]} />)
    expect(err).not.toHaveBeenCalled()
    expect(screen.getAllByRole('listitem').length).toBeGreaterThan(1)
  })

  it('a created session with no lines, totals or link shows just the card', () => {
    render(<CheckoutPanel {...base} sessions={[session({ lines: [], totals: [], continue_url: null })]} />)
    const card = within(screen.getByTestId('cart-shop-a.example.com'))
    expect(card.getByText('cart created')).toBeInTheDocument()
    expect(card.queryByRole('link')).not.toBeInTheDocument()
    expect(card.queryByText(/Total/)).not.toBeInTheDocument()
  })

  it('a total of 0 is shown as $0.00, not hidden', () => {
    render(<CheckoutPanel {...base} sessions={[session({ totals: [{ type: 'total', amount: 0, display_text: '' }] })]} />)
    expect(screen.getByText('$0.00', { selector: 'strong' })).toBeInTheDocument()
    expect(screen.getByText(/^Total:/)).toBeInTheDocument()
  })

  it('a line amount of 0 is shown, a missing one is not', () => {
    render(<CheckoutPanel {...base} sessions={[session({ lines: [{ title: 'Free', quantity: 2, amount: 0 }, { title: 'Unpriced', quantity: 1, amount: null }] })]} />)
    expect(screen.getByText(/2 × Free/)).toHaveTextContent('$0.00')
    expect(screen.getByText(/1 × Unpriced/)).not.toHaveTextContent('$')
  })

  it('unknown message types show their text, or their code when the text is empty', () => {
    render(<CheckoutPanel {...base} sessions={[session({ messages: [{ type: 'weird', code: 'c1', content: 'Something odd' }, { type: 'x', code: 'only_code', content: '' }, { type: '', code: '', content: '' }] })]} />)
    expect(screen.getByText('Something odd')).toBeInTheDocument()
    expect(screen.getByText('only_code')).toBeInTheDocument()
  })

  it.each(['https://', 'javascript:alert(1)', 'http://a.com', 'HTTP://a.com', 'https://user:pw@shop-a.example.com/c', 'https://shop-a.example.com@evil.com/', 'data:text/html,x', ''])('no link for %j', (url) => {
    render(<CheckoutPanel {...base} sessions={[session({ continue_url: url })]} />)
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })

  it('renders an https link (query with a space) opened safely in a new tab', () => {
    render(<CheckoutPanel {...base} sessions={[session({ continue_url: 'https://shop-a.example.com/c?x=a b' })]} />)
    const a = screen.getByRole('link')
    expect(a).toHaveAttribute('target', '_blank')
    expect(a.getAttribute('rel')).toContain('noreferrer')
  })

  it('long and hostile titles are text, not markup, and do not drop the row', () => {
    const title = '<img src=x onerror=alert(1)>' + 'w'.repeat(5000)
    const { container } = render(<CheckoutPanel {...base} sessions={[session({ lines: [{ title, quantity: 1, amount: 1 }], shop: { id: 'x', name: '<b>bold</b>', domain: 'shop-a.example.com' } })]} />)
    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('h4 b')).toBeNull()
    expect(screen.getByText('<b>bold</b>')).toBeInTheDocument()
  })

  it('an empty shop name falls back to the domain, and a failed shop with no reason says so', () => {
    render(<CheckoutPanel {...base} sessions={[session({ shop: { id: 'x', name: '', domain: 'shop-a.example.com' }, status: 'error', cart_id: null, error: null })]} />)
    expect(screen.getByRole('heading', { name: 'shop-a.example.com' })).toBeInTheDocument()
    expect(screen.getByText('The shop did not make a cart.')).toBeInTheDocument()
  })

  it('both buttons are disabled while busy, whatever the sessions', () => {
    const { rerender } = render(<CheckoutPanel {...base} busy="creating" sessions={[session()]} />)
    expect(screen.getByRole('button', { name: 'Cancel carts' })).toBeDisabled()
    rerender(<CheckoutPanel {...base} busy="cancelling" />)
    expect(screen.getByRole('button', { name: 'Cancelling…' })).toBeDisabled()
  })
})

describe('client helpers', () => {
  it('cartRefs only keeps carts that were really made', () => {
    expect(cartRefs([session(), session({ status: 'error' }), session({ cart_id: null }), session({ cart_id: '' }), session({ shop: { id: 'y', name: 'y', domain: 'b.example.com' }, cart_id: 'gid://shopify/Cart/2' })])).toEqual([REF, { domain: 'b.example.com', cart_id: 'gid://shopify/Cart/2' }])
    expect(cartRefs([])).toEqual([])
  })

  it('cancelCartsOnExit does nothing for no carts, no sendBeacon, or a false return', () => {
    const beacon = vi.fn(() => false)
    vi.stubGlobal('navigator', { sendBeacon: beacon })
    cancelCartsOnExit([])
    expect(beacon).not.toHaveBeenCalled()
    expect(() => cancelCartsOnExit([REF])).not.toThrow()
    expect(beacon).toHaveBeenCalledTimes(1)
    vi.stubGlobal('navigator', {})
    expect(() => cancelCartsOnExit([REF])).not.toThrow()
    vi.stubGlobal('navigator', undefined)
    expect(() => cancelCartsOnExit([REF])).not.toThrow()
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
    if (url === '/api/checkout') return (api.checkout ?? (() => json({ sessions: [session()], notice: 'x' })))(body)
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
const makeBtn = () => screen.getByRole('button', { name: /Make a cart at each shop|Making carts/ })
const makeCart = async () => {
  fireEvent.click(makeBtn())
  await screen.findByTestId('cart-shop-a.example.com')
}
const edit = () => fireEvent.change(screen.getByLabelText('Width (in)'), { target: { value: '150' } })
const settle = () => new Promise((r) => setTimeout(r, 50))
const ok = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } })

describe('carts in the app, adversarial', () => {
  beforeEach(() => vi.unstubAllGlobals())

  it('pressing Make a cart twice quickly sends one request', async () => {
    const f = mockApi()
    render(<App />)
    await search()
    fireEvent.click(makeBtn())
    fireEvent.click(makeBtn())
    await screen.findByTestId('cart-shop-a.example.com')
    fireEvent.click(makeBtn())
    await settle()
    expect(to(f, '/api/checkout')).toHaveLength(1)
  })

  it('a swap while carts are being made cancels what arrives', async () => {
    let release!: (r: Response) => void
    const f = mockApi({ checkout: () => new Promise<Response>((res) => (release = res)) })
    render(<App />)
    await search()
    fireEvent.click(makeBtn())
    fireEvent.click(within(screen.getByTestId('slot-desk')).getByRole('button', { name: /Swap/ }))
    fireEvent.click(await screen.findByRole('button', { name: new RegExp(`Use ${BIG_DESK.title}`) }))
    release(ok({ sessions: [session()], notice: 'x' }))
    await waitFor(() => expect(to(f, '/api/checkout/cancel')).toEqual([{ carts: [REF] }]))
    expect(screen.queryByTestId('cart-shop-a.example.com')).not.toBeInTheDocument()
    expect(makeBtn()).toBeEnabled()
  })

  it('only the carts that were really made are cancelled when the room changes', async () => {
    const f = mockApi({ checkout: () => json({ sessions: [session(), session({ shop: { id: 'b', name: 'B', domain: 'b.example.com' }, status: 'error', cart_id: 'gid://shopify/Cart/ghost', error: 'no' })], notice: 'x' }) })
    render(<App />)
    await search()
    await makeCart()
    edit()
    await waitFor(() => expect(to(f, '/api/checkout/cancel')).toEqual([{ carts: [REF] }]))
  })

  it('the cancel button is gone the moment an edit starts the automatic cancel', async () => {
    let release!: (r: Response) => void
    const f = mockApi({ cancel: () => new Promise<Response>((res) => (release = res)) })
    render(<App />)
    await search()
    await makeCart()
    edit()
    expect(screen.getByRole('button', { name: 'Cancel carts' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel carts' }))
    release(ok({ cancelled: 1, failed: 0 }))
    await settle()
    expect(to(f, '/api/checkout/cancel')).toHaveLength(1)
  })

  it('editing while a manual cancel is in flight does not cancel the same carts twice', async () => {
    let release!: (r: Response) => void
    const f = mockApi({ cancel: () => new Promise<Response>((res) => (release = res)) })
    render(<App />)
    await search()
    await makeCart()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel carts' }))
    edit()
    release(ok({ cancelled: 1, failed: 0 }))
    await settle()
    expect(to(f, '/api/checkout/cancel').length).toBeLessThanOrEqual(1)
  })

  it('two pagehide events send the same beacon and never throw', async () => {
    mockApi()
    const beacon = vi.fn(() => true)
    vi.stubGlobal('navigator', { ...navigator, sendBeacon: beacon })
    render(<App />)
    await search()
    await makeCart()
    window.dispatchEvent(new Event('pagehide'))
    window.dispatchEvent(new Event('pagehide'))
    expect(beacon.mock.calls.length).toBeGreaterThanOrEqual(1)
    const bodies = await Promise.all(beacon.mock.calls.map((c) => (c as unknown as [string, Blob])[1].text()))
    expect(new Set(bodies).size).toBe(1)
  })

  it('no beacon after the carts were cancelled by an edit or by the button', async () => {
    mockApi()
    const beacon = vi.fn(() => true)
    vi.stubGlobal('navigator', { ...navigator, sendBeacon: beacon })
    render(<App />)
    await search()
    await makeCart()
    edit()
    await waitFor(() => expect(screen.queryByTestId('cart-shop-a.example.com')).not.toBeInTheDocument())
    window.dispatchEvent(new Event('pagehide'))
    expect(beacon).not.toHaveBeenCalled()
  })

  it('pagehide with sendBeacon missing or returning false does not throw', async () => {
    mockApi()
    vi.stubGlobal('navigator', { ...navigator, sendBeacon: undefined })
    render(<App />)
    await search()
    await makeCart()
    expect(() => window.dispatchEvent(new Event('pagehide'))).not.toThrow()
    vi.stubGlobal('navigator', { ...navigator, sendBeacon: vi.fn(() => false) })
    expect(() => window.dispatchEvent(new Event('pagehide'))).not.toThrow()
    expect(screen.getByTestId('cart-shop-a.example.com')).toBeInTheDocument()
  })

  it.each([
    ['network failure', () => Promise.reject(new Error('down'))],
    ['HTTP 500', () => json({ detail: 'boom' }, 500)],
    ['invalid JSON', () => Promise.resolve(new Response('<html>', { status: 200 }))],
  ])('a cancel that fails on a room edit (%s) is silent and the panel still clears', async (_n, cancel) => {
    const f = mockApi({ cancel })
    render(<App />)
    await search()
    await makeCart()
    edit()
    await waitFor(() => expect(to(f, '/api/checkout/cancel')).toHaveLength(1))
    await settle()
    expect(screen.queryByTestId('cart-shop-a.example.com')).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('a failed manual cancel shows an error and keeps the carts on screen', async () => {
    mockApi({ cancel: () => json({ detail: 'boom' }, 500) })
    render(<App />)
    await search()
    await makeCart()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel carts' }))
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.getByTestId('cart-shop-a.example.com')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancel carts' })).toBeEnabled()
  })

  it('carts can be made again after a cancel, and after a failed attempt', async () => {
    let n = 0
    const f = mockApi({ checkout: () => (n++ === 0 ? Promise.reject(new Error('down')) : json({ sessions: [session()], notice: 'x' })) })
    render(<App />)
    await search()
    fireEvent.click(makeBtn())
    await screen.findByRole('alert')
    await makeCart()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel carts' }))
    await waitFor(() => expect(screen.queryByTestId('cart-shop-a.example.com')).not.toBeInTheDocument())
    await makeCart()
    expect(to(f, '/api/checkout')).toHaveLength(3)
  })

  it('a checkout that answers with no sessions says nothing is chosen and cancels nothing', async () => {
    const f = mockApi({ checkout: () => json({ sessions: [], notice: 'x' }) })
    render(<App />)
    await search()
    fireEvent.click(makeBtn())
    await within(screen.getByRole('region', { name: 'Checkout' })).findByText('Nothing chosen yet.')
    edit()
    await settle()
    expect(to(f, '/api/checkout/cancel')).toHaveLength(0)
  })

  it('unmounting while carts are being made causes no React error output', async () => {
    const err = vi.spyOn(console, 'error').mockImplementation(() => {})
    let release!: (r: Response) => void
    mockApi({ checkout: () => new Promise<Response>((res) => (release = res)) })
    const { unmount } = render(<App />)
    await search()
    fireEvent.click(makeBtn())
    unmount()
    release(ok({ sessions: [session()], notice: 'x' }))
    await settle()
    expect(err).not.toHaveBeenCalled()
  })

  it('no pagehide listener is left behind after unmount', async () => {
    mockApi()
    const beacon = vi.fn(() => true)
    vi.stubGlobal('navigator', { ...navigator, sendBeacon: beacon })
    const { unmount } = render(<App />)
    await search()
    await makeCart()
    unmount()
    window.dispatchEvent(new Event('pagehide'))
    expect(beacon).not.toHaveBeenCalled()
  })
})
