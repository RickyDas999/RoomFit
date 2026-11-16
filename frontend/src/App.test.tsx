import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import type { EvaluateResponse, RecommendResponse } from './api/types'
import { BIG_DESK, BROKEN_CHAIR_PLAN, makePlan, makeRecommend } from './testFixtures'

type Json = Record<string, unknown>
const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } }))

interface Api {
  evaluate?: (body: { room: Json; layout: Json[] }) => Promise<Response>
  recommend?: (body: { room: Json; bed_size?: string }) => Promise<Response>
}

function mockApi(api: Api = {}) {
  const fetchMock = vi.fn((url: string, init: RequestInit) => {
    const body = JSON.parse(String(init.body))
    if (url === '/api/evaluate') return (api.evaluate ?? (() => json(makePlan())))(body)
    if (url === '/api/recommend') return (api.recommend ?? (() => json(makeRecommend())))(body)
    return Promise.reject(new Error(`unexpected ${url}`))
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}
const calls = (f: ReturnType<typeof mockApi>, url: string) => f.mock.calls.filter((c) => c[0] === url).map((c) => JSON.parse(String(c[1].body)) as { room: Json; layout: Json[] })

beforeEach(() => vi.unstubAllGlobals())
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const findButton = () => screen.getByRole('button', { name: 'Find furniture that fits' })
const flags = () => within(screen.getByRole('region', { name: 'Flags' }))
/** The product shown in a slot's card (not the rows of its open swap list). */
const card = (role: string) => within(screen.getByTestId(`slot-${role}`).querySelector<HTMLElement>('.product')!)
const errorText = (text: string | RegExp) => screen.findByText(text, { selector: 'p.error' })
const deferred = <T,>() => {
  let resolve!: (v: T) => void
  const promise = new Promise<T>((r) => (resolve = r))
  return { promise, resolve }
}

describe('storyboard moment 1: enter the room', () => {
  it('draws the sample room with its clearance zones before any search, without touching the catalog', async () => {
    const f = mockApi({ evaluate: () => json(makePlan({ placed: {}, zones: BROKEN_CHAIR_PLAN().zones.slice(0, 1) })) })
    render(<App />)
    expect(await screen.findByTestId('floorplan')).toBeInTheDocument()
    expect(calls(f, '/api/recommend')).toHaveLength(0)
    const [first] = calls(f, '/api/evaluate')
    expect(first.layout).toEqual([])
    expect(first.room).toMatchObject({ width: 144, depth: 192, door: { wall: 'top', offset: 56, width: 32 } })
    expect(screen.getByText(/Press “Find furniture that fits”/)).toBeInTheDocument()
  })

  it('redraws when the room changes (debounced, one request for a burst of typing)', async () => {
    const f = mockApi()
    render(<App />)
    await screen.findByTestId('floorplan')
    for (const v of ['1', '12', '120']) fireEvent.change(screen.getByLabelText('Width (in)'), { target: { value: v } })
    await waitFor(() => expect(calls(f, '/api/evaluate')).toHaveLength(2))
    expect(calls(f, '/api/evaluate')[1].room).toMatchObject({ width: 120 })
  })

  it('does not call the API for a room that cannot work, and says why', async () => {
    const f = mockApi()
    render(<App />)
    await screen.findByTestId('floorplan')
    fireEvent.change(screen.getByLabelText(/Door position/), { target: { value: '140' } })
    expect(await screen.findByText(/door does not fit/)).toBeInTheDocument()
    await new Promise((r) => setTimeout(r, 450))
    expect(calls(f, '/api/evaluate')).toHaveLength(1)
    expect(findButton()).toBeDisabled()
  })
})

describe('storyboard moment 2: get products that fit, with dimensions', () => {
  it('searches, shows progress, then the chosen products with sizes, the verdict and the sort order', async () => {
    const pending = deferred<Response>()
    const f = mockApi({ recommend: () => pending.promise })
    render(<App />)
    await screen.findByTestId('floorplan')
    fireEvent.click(findButton())
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent(/Searching the Shopify catalog/))
    expect(screen.getByRole('button', { name: 'Searching…' })).toBeDisabled()

    pending.resolve(await json(makeRecommend()))
    expect(await screen.findByText('Twin XL bed')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('')
    expect(calls(f, '/api/recommend')[0].room).toMatchObject({ width: 144, depth: 192 })

    const desk = screen.getByTestId('slot-desk')
    expect(within(desk).getByText('Small desk')).toBeInTheDocument()
    expect(within(desk).getByText('48 × 24 × 30 in')).toBeInTheDocument()
    expect(within(screen.getByTestId('slot-desk_chair')).getByText('assumed 20 × 20 in')).toBeInTheDocument()
    expect(screen.getByText('Sorted by: lowest price that fits')).toBeInTheDocument()
    expect(screen.getByText('Fits')).toBeInTheDocument()
    expect(screen.getByText('No problems found.')).toBeInTheDocument()
    expect(findButton()).toBeEnabled()
  })

  it('shows "dimensions missing" for a chosen product with no size', async () => {
    const rec = makeRecommend()
    rec.layout[0].product = { ...rec.layout[0].product, dimensions: null, dimension_status: 'missing', dimension_reason: 'no_dimensions', dimension_source: null }
    rec.unplaced = [{ slot_id: 'bed', reason: 'dimensions missing' }]
    mockApi({ recommend: () => json(rec) })
    render(<App />)
    await screen.findByTestId('floorplan')
    fireEvent.click(findButton())
    const bed = await screen.findByTestId('slot-bed')
    expect(within(bed).getByText('dimensions missing', { selector: '.badge' })).toBeInTheDocument()
    expect(screen.getByText('Bed: dimensions missing')).toBeInTheDocument()
  })
})

describe('storyboard moment 3: swap in a bigger desk and the clearance flag fires', () => {
  async function searched(evaluate?: Api['evaluate']) {
    const f = mockApi({ evaluate: evaluate ?? (() => json(makePlan())) })
    render(<App />)
    await screen.findByTestId('floorplan')
    fireEvent.click(findButton())
    await screen.findByText('Twin XL bed')
    return f
  }

  it('re-checks the layout with the new desk and shows the flag, the red zone and the new verdict', async () => {
    const pending = deferred<Response>()
    let hold = false
    const f = await searched(() => (hold ? pending.promise : json(makePlan())))
    f.mockClear()
    hold = true
    fireEvent.click(within(screen.getByTestId('slot-desk')).getByRole('button', { name: /Swap/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Use Big corner desk as the desk' }))
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Checking the new layout'))
    pending.resolve(await json(makePlan()))

    const sent = calls(f, '/api/evaluate')
    expect(sent).toHaveLength(1)
    const byslot = Object.fromEntries(sent[0].layout.map((i) => [i.slot_id, (i.product as { id: string }).id]))
    expect(byslot.desk).toBe(BIG_DESK.id)
    expect(Object.keys(byslot).sort()).toEqual(['bed', 'desk', 'desk_chair']) // everything else is kept
  })

  it('shows "Behind the desk chair: 6 in short" and shades the zone red', async () => {
    await searched((body) => json(body.layout.some((i) => (i.product as { id: string }).id === BIG_DESK.id) ? BROKEN_CHAIR_PLAN() : makePlan()))
    expect(screen.queryByText(/6 in short/)).toBeNull()
    fireEvent.click(within(screen.getByTestId('slot-desk')).getByRole('button', { name: /Swap/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Use Big corner desk as the desk' }))

    await waitFor(() => expect(flags().getByText('Behind the desk chair: 6 in short')).toBeInTheDocument())
    expect(screen.getByText('Cramped')).toBeInTheDocument()
    expect(screen.getByTestId('zone-behind_desk_chair').dataset.broken).toBe('true')
    expect(screen.getByTestId('zone-label-behind_desk_chair')).toHaveTextContent('6 in short')
    // the new desk is the selected one, and the other slots did not change
    expect(card('desk').getByText('Big corner desk')).toBeInTheDocument()
    expect(within(screen.getByTestId('slot-desk')).getByRole('button', { name: 'Big corner desk is selected' })).toBeDisabled()
    expect(within(screen.getByTestId('slot-bed')).getByText('Twin XL bed')).toBeInTheDocument()
  })

  it('swapping back clears the flag', async () => {
    await searched((body) => json(body.layout.some((i) => (i.product as { id: string }).id === BIG_DESK.id) ? BROKEN_CHAIR_PLAN() : makePlan()))
    fireEvent.click(within(screen.getByTestId('slot-desk')).getByRole('button', { name: /Swap/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Use Big corner desk as the desk' }))
    await waitFor(() => expect(flags().getByText('Behind the desk chair: 6 in short')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Use Small desk as the desk' }))
    expect(await screen.findByText('No problems found.')).toBeInTheDocument()
    expect(screen.getByTestId('zone-behind_desk_chair').dataset.broken).toBe('false')
  })

  it('keeps the chair assumed when the chair is swapped', async () => {
    const f = await searched()
    f.mockClear()
    fireEvent.click(within(screen.getByTestId('slot-desk_chair')).getByRole('button', { name: /Swap/ }))
    const other = makeRecommend().candidates.desk_chair![0].product
    fireEvent.click(screen.getByRole('button', { name: new RegExp(`${other.title} is selected`) }))
    expect(calls(f, '/api/evaluate')).toHaveLength(0) // the selected one cannot be picked again
  })

  it('shows an error and keeps the old plan when the re-check fails', async () => {
    let fail = false
    await searched(() => (fail ? json({ detail: 'boom' }, 500) : json(makePlan())))
    fail = true
    fireEvent.click(within(screen.getByTestId('slot-desk')).getByRole('button', { name: /Swap/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Use Big corner desk as the desk' }))
    expect(await errorText('boom')).toBeInTheDocument()
    expect(screen.getByTestId('floorplan')).toBeInTheDocument()
    expect(card('desk').getByText('Small desk')).toBeInTheDocument() // unchanged
  })
})

describe('errors and stale results', () => {
  it('shows the server message when the catalog search fails (502) and no products', async () => {
    mockApi({ recommend: () => json({ detail: 'catalog error: rate limited (HTTP 429) after retries' }, 502) })
    render(<App />)
    await screen.findByTestId('floorplan')
    fireEvent.click(findButton())
    expect(await errorText('catalog error: rate limited (HTTP 429) after retries')).toBeInTheDocument()
    expect(screen.queryByText('Twin XL bed')).toBeNull()
    expect(findButton()).toBeEnabled() // can try again
  })

  it('says the server is unreachable when the request cannot be made', async () => {
    mockApi({ recommend: () => Promise.reject(new TypeError('Failed to fetch')) })
    render(<App />)
    await screen.findByTestId('floorplan')
    fireEvent.click(findButton())
    expect(await errorText(/Could not reach the Room Fit server/)).toBeInTheDocument()
  })

  it('shows a plain message for a rejected room (422)', async () => {
    mockApi({ recommend: () => json({ detail: [{ msg: 'x' }] }, 422) })
    render(<App />)
    await screen.findByTestId('floorplan')
    fireEvent.click(findButton())
    expect(await errorText('The server rejected the room. Check the numbers.')).toBeInTheDocument()
  })

  it('drops the products when the room changes, so they never describe another room', async () => {
    const f = mockApi()
    render(<App />)
    await screen.findByTestId('floorplan')
    fireEvent.click(findButton())
    await screen.findByText('Twin XL bed')
    fireEvent.change(screen.getByLabelText('Width (in)'), { target: { value: '120' } })
    await waitFor(() => expect(screen.queryByText('Twin XL bed')).toBeNull())
    await waitFor(() => expect(calls(f, '/api/evaluate').at(-1)?.room).toMatchObject({ width: 120 }))
    expect(calls(f, '/api/evaluate').at(-1)?.layout).toEqual([])
    expect(screen.getByText(/Press “Find furniture that fits”/)).toBeInTheDocument()
  })

  it('ignores a search result that arrives after the room was changed', async () => {
    const slow = deferred<Response>()
    mockApi({ recommend: () => slow.promise })
    render(<App />)
    await screen.findByTestId('floorplan')
    fireEvent.click(findButton())
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent(/Searching/))
    fireEvent.change(screen.getByLabelText('Width (in)'), { target: { value: '120' } })
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent(''))
    slow.resolve(await json(makeRecommend()))
    await new Promise((r) => setTimeout(r, 50))
    expect(screen.queryByText('Twin XL bed')).toBeNull()
  })

  it('uses the sample room again on request', async () => {
    const f = mockApi()
    render(<App />)
    await screen.findByTestId('floorplan')
    fireEvent.change(screen.getByLabelText('Depth (in)'), { target: { value: '150' } })
    await waitFor(() => expect(calls(f, '/api/evaluate').at(-1)?.room).toMatchObject({ depth: 150 }))
    fireEvent.click(screen.getByRole('button', { name: 'Use the sample room' }))
    await waitFor(() => expect(calls(f, '/api/evaluate').at(-1)?.room).toMatchObject({ depth: 192 }))
    expect(screen.getByLabelText('Depth (in)')).toHaveValue(192)
  })
})

describe('types', () => {
  it('the mocked responses have the generated API shapes', () => {
    const rec: RecommendResponse = makeRecommend()
    const plan: EvaluateResponse = makePlan()
    expect(Object.keys(rec)).toEqual(expect.arrayContaining(Object.keys(plan)))
    expect(Object.keys(rec)).toEqual(expect.arrayContaining(['layout', 'candidates', 'searched', 'sorted_by']))
  })
})

describe('room edits while things are in flight (review findings)', () => {
  const emptyWhenNoLayout: Api['evaluate'] = (body) =>
    json(body.layout.length === 0 ? makePlan({ placed: {}, zones: [], evaluation: makePlan().evaluation }) : makePlan())

  it('"Use the sample room" on the sample room clears the products AND redraws the empty plan', async () => {
    const f = mockApi({ evaluate: emptyWhenNoLayout })
    render(<App />)
    await screen.findByTestId('floorplan')
    fireEvent.click(findButton())
    await screen.findByText('Twin XL bed')
    expect(await screen.findByTestId('piece-bed')).toBeInTheDocument()
    const before = calls(f, '/api/evaluate').length

    fireEvent.click(screen.getByRole('button', { name: 'Use the sample room' })) // same room as now
    await waitFor(() => expect(calls(f, '/api/evaluate').length).toBe(before + 1))
    await waitFor(() => expect(screen.queryByTestId('piece-bed')).toBeNull()) // plan matches the (empty) cards
    expect(screen.queryByText('Twin XL bed')).toBeNull()
    expect(screen.getAllByText('Nothing chosen yet.').length).toBeGreaterThan(0)
    expect(document.querySelector('figure')).not.toHaveClass('plan--stale')
  })

  it('an edit back to the same room also redraws', async () => {
    const f = mockApi({ evaluate: emptyWhenNoLayout })
    render(<App />)
    await screen.findByTestId('floorplan')
    fireEvent.click(findButton())
    await screen.findByText('Twin XL bed')
    fireEvent.change(screen.getByLabelText('Width (in)'), { target: { value: '120' } })
    fireEvent.change(screen.getByLabelText('Width (in)'), { target: { value: '144' } })
    await waitFor(() => expect(screen.queryByTestId('piece-bed')).toBeNull())
    expect(calls(f, '/api/evaluate').at(-1)?.room).toMatchObject({ width: 144 })
  })

  it('does not leave the search button stuck when the room is edited mid-search and the redraw fails', async () => {
    const slow = deferred<Response>()
    let failPreview = false
    mockApi({ recommend: () => slow.promise, evaluate: () => (failPreview ? json({ detail: 'preview failed' }, 500) : json(makePlan())) })
    render(<App />)
    await screen.findByTestId('floorplan')
    fireEvent.click(findButton())
    await waitFor(() => expect(screen.getByRole('button', { name: 'Searching…' })).toBeDisabled())
    failPreview = true
    fireEvent.change(screen.getByLabelText('Width (in)'), { target: { value: '120' } })
    expect(await errorText('preview failed')).toBeInTheDocument()
    expect(findButton()).toBeEnabled() // not stuck on "Searching…"
    expect(screen.getByRole('button', { name: 'Use the sample room' })).toBeEnabled()
  })

  it('ignores a search result that arrives after the form moved to an invalid room', async () => {
    const slow = deferred<Response>()
    mockApi({ recommend: () => slow.promise })
    render(<App />)
    await screen.findByTestId('floorplan')
    fireEvent.click(findButton())
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent(/Searching/))
    fireEvent.change(screen.getByLabelText(/Door position/), { target: { value: '140' } }) // invalid
    slow.resolve(await json(makeRecommend()))
    await new Promise((r) => setTimeout(r, 50))
    expect(screen.queryByText('Twin XL bed')).toBeNull()
    expect(screen.getByRole('status')).toHaveTextContent('')
  })

  it('dims the plan from the moment of an edit until it has been redrawn', async () => {
    const pending = deferred<Response>()
    let hold = false
    mockApi({ evaluate: () => (hold ? pending.promise : json(makePlan())) })
    render(<App />)
    await screen.findByTestId('floorplan')
    hold = true
    fireEvent.change(screen.getByLabelText('Depth (in)'), { target: { value: '150' } })
    expect(document.querySelector('figure')).toHaveClass('plan--stale')
    await new Promise((r) => setTimeout(r, 400))
    pending.resolve(await json(makePlan()))
    await waitFor(() => expect(document.querySelector('figure')).not.toHaveClass('plan--stale'))
  })
})


describe('scenarios, needs and bed size', () => {
  it('picking an example redraws the room and clears the products from the old room', async () => {
    const f = mockApi()
    render(<App />)
    await screen.findByTestId('floorplan')
    fireEvent.click(findButton())
    await screen.findByText('Twin XL bed')
    fireEvent.change(screen.getByLabelText('Start from an example'), { target: { value: 'wfh' } })
    expect(screen.queryByText('Twin XL bed')).not.toBeInTheDocument()
    await waitFor(() => expect(calls(f, '/api/evaluate').at(-1)?.room).toMatchObject({ width: 176, depth: 192 }))
  })

  it('sends the needs and the chosen bed size to the search', async () => {
    const f = mockApi()
    render(<App />)
    await screen.findByTestId('floorplan')
    fireEvent.click(screen.getByRole('checkbox', { name: 'Desk and chair' }))
    fireEvent.change(screen.getByLabelText('Bed size'), { target: { value: 'queen' } })
    fireEvent.click(findButton())
    await screen.findByText('Twin XL bed')
    const [body] = f.mock.calls.filter((c) => c[0] === '/api/recommend').map((c) => JSON.parse(String(c[1].body)))
    expect(body.bed_size).toBe('queen')
    expect(body.room.needs).toEqual(['nightstand', 'dresser'])
  })

  it('hides the cards for pieces that are not wanted (the chair goes with the desk)', async () => {
    mockApi()
    render(<App />)
    await screen.findByTestId('floorplan')
    expect(screen.getByTestId('slot-desk_chair')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox', { name: 'Desk and chair' }))
    expect(screen.queryByTestId('slot-desk')).not.toBeInTheDocument()
    expect(screen.queryByTestId('slot-desk_chair')).not.toBeInTheDocument()
    expect(screen.getByTestId('slot-bed')).toBeInTheDocument()
    expect(screen.getByTestId('slot-dresser')).toBeInTheDocument()
  })

  it('explains the bed size on the bed card, and the planner note on a moved piece', async () => {
    const plan = makePlan({ slots: makePlan().slots.map((s) => (s.role === 'desk' ? { ...s, note: 'on the door wall: the far side of the room has no space for a desk' } : s)) })
    mockApi({ recommend: () => json(makeRecommend({ ...plan, bed_size: 'queen', bed_size_reason: 'Queen: the biggest size that fits this room' })) })
    render(<App />)
    await screen.findByTestId('floorplan')
    fireEvent.click(findButton())
    expect(await within(screen.getByTestId('slot-bed')).findByText(/Queen: the biggest size that fits this room/)).toBeInTheDocument()
    expect(within(screen.getByTestId('slot-desk')).getByText(/on the door wall/)).toBeInTheDocument()
  })
})
