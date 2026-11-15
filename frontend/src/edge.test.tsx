import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { CoverageMeter } from './components/Flags'
import { FloorPlan } from './components/FloorPlan'
import { SlotCard } from './components/SlotCard'
import { doorGeometry } from './floorplan'
import { makeRoom } from './edgeHelpers'
import { SAMPLE_FORM, toRoom, validate } from './room'
import { BIG_DESK, cand, makePlan, makeProduct, makeRecommend, makeSlots, missing, SMALL_DESK } from './testFixtures'

type Json = Record<string, unknown>
const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } }))
const deferred = <T,>() => {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((a, b) => ((resolve = a), (reject = b)))
  return { promise, resolve, reject }
}
function mockApi(api: { evaluate?: (b: { room: Json; layout: Json[] }) => Promise<Response>; recommend?: (b: { room: Json }) => Promise<Response> } = {}) {
  const f = vi.fn((url: string, init: RequestInit) => {
    const body = JSON.parse(String(init.body))
    if (url === '/api/evaluate') return (api.evaluate ?? (() => json(makePlan())))(body)
    if (url === '/api/recommend') return (api.recommend ?? (() => json(makeRecommend())))(body)
    return Promise.reject(new Error(`unexpected ${url}`))
  })
  vi.stubGlobal('fetch', f)
  return f
}
beforeEach(() => vi.unstubAllGlobals())
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})
const findButton = () => screen.getByRole('button', { name: /Find furniture that fits|Searching/ })
const setWidth = (v: string) => fireEvent.change(screen.getByLabelText('Width (in)'), { target: { value: v } })

describe('App races', () => {

  it('recommend result arriving after the room was edited is dropped and busy clears', async () => {
    const slow = deferred<Response>()
    mockApi({ recommend: () => slow.promise })
    render(<App />)
    await screen.findByTestId('floorplan')
    fireEvent.click(findButton())
    setWidth('150')
    await act(async () => slow.resolve(await json(makeRecommend())))
    await waitFor(() => expect(findButton()).toBeEnabled())
    await waitFor(() => expect(screen.queryByText('Twin XL bed')).toBeNull())
  })

  it('BUG? preview evaluate failing while a search was pending must not leave the form stuck on "Searching"', async () => {
    const slow = deferred<Response>()
    mockApi({
      recommend: () => slow.promise,
      evaluate: (b) => (Number(b.room.width) === 150 ? json({ detail: 'boom' }, 500) : json(makePlan())),
    })
    render(<App />)
    await screen.findByTestId('floorplan')
    fireEvent.click(findButton())
    setWidth('150')
    await screen.findByText('boom', { selector: 'p.error' })
    await act(async () => slow.resolve(await json(makeRecommend())))
    // the stale search was discarded; the button must be usable again once the user fixes the room
    await waitFor(() => expect(screen.getByRole('button', { name: 'Find furniture that fits' })).toBeEnabled())
  })

  it('preview evaluate failing then succeeding clears the error', async () => {
    let fail = true
    mockApi({ evaluate: () => (fail ? json({ detail: 'nope' }, 502) : json(makePlan())) })
    render(<App />)
    await screen.findByText('nope', { selector: 'p.error' })
    fail = false
    setWidth('145')
    await screen.findByTestId('floorplan')
    expect(screen.queryByText('nope')).toBeNull()
  })

  it('unmount during a pending request logs no errors', async () => {
    const slow = deferred<Response>()
    const err = vi.spyOn(console, 'error').mockImplementation(() => {})
    mockApi({ recommend: () => slow.promise })
    const { unmount } = render(<App />)
    await screen.findByTestId('floorplan')
    fireEvent.click(findButton())
    unmount()
    await act(async () => slow.resolve(await json(makeRecommend())))
    expect(err).not.toHaveBeenCalled()
  })

  it('unmount inside the debounce window does not fire a request', async () => {
    vi.useFakeTimers()
    const f = mockApi()
    const { unmount } = render(<App />)
    unmount()
    await vi.advanceTimersByTimeAsync(1000)
    vi.useRealTimers()
    expect(f).not.toHaveBeenCalled()
  })

  it('a non-ApiError (200 with bad JSON) shows a friendly message, not raw SyntaxError text', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response('<html>', { status: 200 }))))
    render(<App />)
    const alert = await screen.findByRole('alert', {}, { timeout: 2000 })
    expect(alert.textContent).not.toMatch(/Unexpected token/)
  })
})

describe('room form edge input', () => {
  const form = (over: Partial<typeof SAMPLE_FORM>) => ({ ...SAMPLE_FORM, ...over })
  it('rejects negatives, NaN, Infinity, zero', () => {
    for (const o of [{ width: -5 }, { depth: 0 }, { width: NaN }, { depth: Infinity }, { doorOffset: -1 }, { windowOffset: 1e9 }]) {
      expect(validate(form(o)).length, JSON.stringify(o)).toBeGreaterThan(0)
    }
  })
  it('door at offset 0 and at the far end is valid; one inch past is not', () => {
    expect(validate(form({ doorOffset: 0 }))).toEqual([])
    expect(validate(form({ doorOffset: 144 - 32 }))).toEqual([])
    expect(validate(form({ doorOffset: 144 - 32 + 1 }))).not.toEqual([])
  })
  it('door geometry at ends stays on the wall', () => {
    const g0 = doorGeometry(toRoom(form({ doorOffset: 0 })))
    expect(g0.start).toEqual({ x: 0, y: 0 })
    const g1 = doorGeometry(toRoom(form({ doorOffset: 112 })))
    expect(g1.end).toEqual({ x: 144, y: 0 })
    expect(g1.arc).not.toMatch(/NaN/)
  })
  it('decimals: a 0.5 in room or fractional offsets are accepted without NaN in the SVG', () => {
    const room = toRoom(form({ width: 144.5, depth: 192.25, doorOffset: 10.5 }))
    const { container } = render(<FloorPlan room={room} plan={makePlan()} />)
    expect(container.innerHTML).not.toMatch(/NaN|undefined/)
  })
  it('huge room renders', () => {
    const room = toRoom(form({ width: 1e7, depth: 1e7, doorOffset: 0 }))
    const { container } = render(<FloorPlan room={room} plan={makePlan()} />)
    expect(container.innerHTML).not.toMatch(/NaN|Infinity/)
  })
  it('closet too big for a tiny room is flagged, not sent', () => {
    expect(validate(form({ width: 40, depth: 40, doorOffset: 0, windowOffset: 0, closet: true })).join()).toMatch(/closet|door|window/)
    expect(validate(form({ width: 40, depth: 40, doorOffset: 0, windowOffset: 0, closet: true })).join()).toMatch(/closet/)
  })
  it('clearing a field shows "Fill in every number" and disables submit; no request while invalid', async () => {
    const f = mockApi()
    render(<App />)
    await screen.findByTestId('floorplan')
    const before = f.mock.calls.length
    setWidth('')
    expect(screen.getByText('Fill in every number.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Find furniture that fits' })).toBeDisabled()
    await new Promise((r) => setTimeout(r, 450))
    expect(f.mock.calls.length).toBe(before)
  })
  it('rapid edits send only the last room', async () => {
    const f = mockApi()
    render(<App />)
    await screen.findByTestId('floorplan')
    f.mockClear()
    for (const v of ['100', '110', '120', '130']) setWidth(v)
    await waitFor(() => expect(f).toHaveBeenCalled())
    await new Promise((r) => setTimeout(r, 450))
    expect(f).toHaveBeenCalledTimes(1)
    expect(JSON.parse(String(f.mock.calls[0][1].body)).room.width).toBe(130)
  })
})

describe('accessibility', () => {
  it('every input has an accessible label and every button a name', async () => {
    mockApi()
    const { container } = render(<App />)
    await screen.findByTestId('floorplan')
    fireEvent.click(findButton())
    await screen.findByText('Small desk')
    for (const b of screen.getAllByRole('button')) expect(b).toHaveAccessibleName()
    for (const i of container.querySelectorAll('input')) expect(i, i.outerHTML).toHaveAccessibleName()
    const ids = [...container.querySelectorAll('[id]')].map((e) => e.id)
    expect(new Set(ids).size).toBe(ids.length)
  })
  it('several SlotCards open at once have unique list ids wired to aria-controls', async () => {
    mockApi()
    render(<App />)
    await screen.findByTestId('floorplan')
    fireEvent.click(findButton())
    await screen.findByText('Small desk')
    const toggles = screen.getAllByRole('button', { name: /Swap \(/ })
    expect(toggles.length).toBeGreaterThan(1)
    toggles.forEach((t) => fireEvent.click(t))
    const ids = screen.getAllByRole('button', { name: /Hide alternatives/ }).map((b) => {
      expect(b).toHaveAttribute('aria-expanded', 'true')
      const id = b.getAttribute('aria-controls')!
      expect(document.getElementById(id)).not.toBeNull()
      return id
    })
    expect(new Set(ids).size).toBe(ids.length)
  })
  it('collapsed toggle: aria-controls target need not exist but aria-expanded=false', () => {
    render(<SlotCard slot={makeSlots().find((s) => s.role === 'desk')!} candidates={[cand(SMALL_DESK)]} busy={false} onSwap={() => {}} />)
    expect(screen.getByRole('button', { name: /Swap/ })).toHaveAttribute('aria-expanded', 'false')
  })
  it('role=meter values are clamped and consistent', () => {
    const ev = { ...makePlan().evaluation, coverage_pct: 80, coverage_status: 'flag' as const }
    render(<CoverageMeter evaluation={ev} />)
    const m = screen.getByRole('meter')
    expect(Number(m.getAttribute('aria-valuenow'))).toBeLessThanOrEqual(Number(m.getAttribute('aria-valuemax')))
    expect(m).toHaveAccessibleName(/Floor covered/)
  })
  it('long-decimal coverage is rounded for display', () => {
    render(<CoverageMeter evaluation={{ ...makePlan().evaluation, coverage_pct: 20.833333333333332 }} />)
    expect(screen.getByRole('meter').getAttribute('aria-valuetext')).not.toMatch(/\d{4,}/)
  })
})

describe('untrusted product content', () => {
  const evil = '<img src=x onerror="window.__xss=1"><script>window.__xss=1</script>'
  it('titles, shop names, snippets render as text', () => {
    const p = makeProduct('x', { title: evil, shop: { id: 's', name: evil, domain: evil }, dimension_source: evil })
    const { container } = render(
      <SlotCard slot={makeSlots().find((s) => s.role === 'desk')!} item={{ slot_id: 'desk', product: p, footprint_basis: 'parsed' }} candidates={[cand(p)]} busy={false} onSwap={() => {}} />,
    )
    fireEvent.click(screen.getByRole('button', { name: /Swap/ }))
    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('img[src="x"]')).toBeNull()
    expect(container.textContent).toContain(evil)
    expect((window as unknown as Json).__xss).toBeUndefined()
  })
  it('javascript: product url is not linked', () => {
    const p = makeProduct('x', { url: 'javascript:alert(1)' })
    render(<SlotCard slot={makeSlots()[1]} item={{ slot_id: 'desk', product: p, footprint_basis: 'parsed' }} candidates={[]} busy={false} onSwap={() => {}} />)
    expect(screen.queryByRole('link')).toBeNull()
  })
  it('null image_url/url and missing shop name do not crash or print "null"/"undefined"', () => {
    const p = makeProduct('x', { image_url: null, url: null as never, shop: { id: 's', name: null as never, domain: null as never } })
    const { container } = render(<SlotCard slot={makeSlots()[1]} item={{ slot_id: 'desk', product: p, footprint_basis: 'parsed' }} candidates={[cand(p)]} busy={false} onSwap={() => {}} />)
    expect(container.textContent).not.toMatch(/null|undefined/)
  })
  it('25 candidates render with unique keys and no console errors', () => {
    const err = vi.spyOn(console, 'error').mockImplementation(() => {})
    const cs = Array.from({ length: 25 }, (_, i) => cand(i % 3 ? makeProduct(`c${i}`) : missing(`c${i}`)))
    render(<SlotCard slot={makeSlots()[1]} candidates={cs} busy={false} onSwap={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: 'Swap (25 found)' }))
    expect(screen.getAllByRole('listitem')).toHaveLength(25)
    expect(err).not.toHaveBeenCalled()
  })
  it('selected candidate with the same id as another is the only one marked', () => {
    render(<SlotCard slot={makeSlots()[1]} item={{ slot_id: 'desk', product: SMALL_DESK, footprint_basis: 'parsed' }} candidates={[cand(SMALL_DESK), cand(BIG_DESK, false)]} busy={false} onSwap={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: /Swap/ }))
    expect(screen.getAllByRole('button', { name: /is selected/ })).toHaveLength(1)
  })
})

describe('plan / layout mismatches', () => {
  it('a layout item whose slot is missing from plan.slots does not crash the App', async () => {
    const rec = makeRecommend({ slots: makeSlots().filter((s) => s.role !== 'desk') })
    mockApi({ recommend: () => json(rec) })
    render(<App />)
    await screen.findByTestId('floorplan')
    fireEvent.click(findButton())
    await screen.findByText('Twin XL bed')
    expect(screen.queryByTestId('slot-desk')).toBeNull()
  })
  it('zero-width room draws without NaN', () => {
    const room = { ...makeRoom(), width: 0 }
    const { container } = render(<FloorPlan room={room} plan={makePlan({ placed: {}, zones: [] })} />)
    expect(container.innerHTML).not.toMatch(/NaN/)
  })
})
