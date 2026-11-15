import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { RoomFormView } from './components/RoomForm'
import { SAMPLE_FORM, type RoomForm } from './room'
import { SCENARIOS, matchScenario } from './scenarios'
import { makePlan, makeRecommend } from './testFixtures'

const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } }))
const deferred = <T,>() => {
  let resolve!: (v: T) => void
  const promise = new Promise<T>((r) => (resolve = r))
  return { promise, resolve }
}

function mockApi(recommend?: () => Promise<Response>) {
  const f = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>((url) => {
    if (url === '/api/evaluate') return json(makePlan())
    if (url === '/api/recommend') return (recommend ?? (() => json(makeRecommend())))()
    return Promise.reject(new Error(`unexpected ${url}`))
  })
  vi.stubGlobal('fetch', f)
  return f
}

beforeEach(() => vi.unstubAllGlobals())
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const find = () => screen.getByRole('button', { name: 'Find furniture that fits' })
const pick = (id: string) => fireEvent.change(screen.getByLabelText('Start from an example'), { target: { value: id } })

describe('scenario picker and in-flight searches', () => {
  it('picking an example during a search drops the stale result', async () => {
    const slow = deferred<Response>()
    mockApi(() => slow.promise)
    render(<App />)
    await screen.findByTestId('floorplan')
    fireEvent.click(find())
    await screen.findByText(/Searching the Shopify catalog/)
    pick('wfh')
    expect(screen.queryByText(/Searching the Shopify catalog/)).not.toBeInTheDocument()
    expect(find()).toBeEnabled()
    slow.resolve(await json(makeRecommend()))
    await new Promise((r) => setTimeout(r, 50))
    expect(screen.queryByText('Twin XL bed')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Width (in)')).toHaveValue(176)
  })

  it('changing the bed size clears the products and the bed explanation', async () => {
    mockApi(() => json(makeRecommend({ bed_size: 'twin_xl', bed_size_reason: 'Twin XL: the biggest size that fits this room' })))
    render(<App />)
    await screen.findByTestId('floorplan')
    fireEvent.click(find())
    expect(await screen.findByText('Twin XL bed')).toBeInTheDocument()
    expect(screen.getByText(/the biggest size that fits this room/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Bed size'), { target: { value: 'king' } })
    expect(screen.queryByText('Twin XL bed')).not.toBeInTheDocument()
    expect(screen.queryByText(/the biggest size that fits this room/)).not.toBeInTheDocument()
  })

  it('toggling a need off and on hides and shows its cards, and the search body follows', async () => {
    const f = mockApi()
    render(<App />)
    await screen.findByTestId('floorplan')
    const dresser = screen.getByRole('checkbox', { name: 'Dresser' })
    fireEvent.click(dresser)
    expect(screen.queryByTestId('slot-dresser')).not.toBeInTheDocument()
    fireEvent.click(dresser)
    expect(screen.getByTestId('slot-dresser')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox', { name: 'Nightstand' }))
    fireEvent.click(screen.getByRole('checkbox', { name: 'Desk and chair' }))
    fireEvent.click(screen.getByRole('checkbox', { name: 'Dresser' }))
    expect(screen.getAllByTestId(/^slot-/)).toHaveLength(1) // only the bed
    fireEvent.click(find())
    await screen.findByText('Twin XL bed')
    const body = JSON.parse(String(f.mock.calls.find((c) => c[0] === '/api/recommend')![1]!.body))
    expect(body.room.needs).toEqual([])
    // the stale server answer still has desk and dresser data, but their cards stay hidden
    expect(screen.queryByTestId('slot-desk')).not.toBeInTheDocument()
  })

  it('the picker shows Custom after any edit, and the preset again when edited back', async () => {
    mockApi()
    render(<App />)
    await screen.findByTestId('floorplan')
    const sel = screen.getByLabelText('Start from an example')
    expect(sel).toHaveValue('starter')
    fireEvent.click(screen.getByRole('checkbox', { name: 'Closet (48 x 24 in, in the corner at the start of the door wall)' }))
    expect(sel).toHaveValue('')
    expect(within(sel).getByRole('option', { name: 'Custom room' })).toBeDisabled()
    fireEvent.click(screen.getByRole('checkbox', { name: 'Closet (48 x 24 in, in the corner at the start of the door wall)' }))
    expect(sel).toHaveValue('starter')
    fireEvent.change(screen.getByLabelText('Bed size'), { target: { value: 'full' } })
    expect(sel).toHaveValue('')
  })

  it('every scenario can be picked and selected back', async () => {
    mockApi()
    render(<App />)
    await screen.findByTestId('floorplan')
    for (const sc of SCENARIOS) {
      pick(sc.id)
      expect(screen.getByLabelText('Start from an example')).toHaveValue(sc.id)
      expect(screen.getByLabelText('Width (in)')).toHaveValue(sc.form.width)
    }
  })
})

describe('matchScenario edge cases', () => {
  it('ignores needs order but not a duplicated or extra need', () => {
    const small = SCENARIOS.find((s) => s.id === 'small')!
    expect(matchScenario({ ...small.form, needs: ['dresser', 'nightstand'] })?.id).toBe('small')
    expect(matchScenario({ ...small.form, needs: ['dresser', 'nightstand', 'desk'] })?.id).not.toBe('small')
    expect(matchScenario({ ...small.form, needs: ['dresser'] })).toBeUndefined()
  })

  it('does not match a NaN field (a half-typed form)', () => {
    expect(matchScenario({ ...SAMPLE_FORM, width: Number.NaN })).toBeUndefined()
  })

  it('does not mutate the form needs when matching', () => {
    const needs: RoomForm['needs'] = ['desk', 'dresser', 'nightstand']
    matchScenario({ ...SAMPLE_FORM, needs })
    expect(needs).toEqual(['desk', 'dresser', 'nightstand'])
  })
})

describe('keyboard accessibility of the new controls', () => {
  const setup = (form: RoomForm = SAMPLE_FORM) => {
    const onChange = vi.fn()
    render(<RoomFormView form={form} errors={[]} busy={false} onChange={onChange} onReset={vi.fn()} onSubmit={vi.fn()} />)
    return onChange
  }

  it('need checkboxes are native focusable checkboxes (space toggles natively); the always-on bed is skipped', () => {
    const onChange = setup()
    const group = screen.getByRole('group', { name: 'What do you need?' })
    const boxes = within(group).getAllByRole('checkbox')
    expect(boxes).toHaveLength(4)
    expect(boxes[0]).toBeDisabled()
    for (const b of boxes.slice(1)) {
      expect(b.tagName).toBe('INPUT')
      expect(b).not.toHaveAttribute('tabindex', '-1')
      b.focus()
      expect(b).toHaveFocus()
    }
    boxes[1].focus()
    fireEvent.click(boxes[1]) // what the browser does for Space on a focused checkbox
    expect(onChange).toHaveBeenCalledWith({ ...SAMPLE_FORM, needs: ['dresser', 'desk'] })
  })

  it('the selects are labelled, focusable, described, and every option has a name', () => {
    setup()
    const scenario = screen.getByRole('combobox', { name: 'Start from an example' })
    const bed = screen.getByRole('combobox', { name: 'Bed size' })
    scenario.focus()
    expect(scenario).toHaveFocus()
    expect(scenario).toHaveAccessibleDescription(/12 x 16 ft with a closet/)
    for (const o of within(bed).getAllByRole('option')) expect(o).toHaveAccessibleName()
    expect(within(bed).getAllByRole('option').map((o) => o.getAttribute('value'))).toEqual(['auto', 'twin_xl', 'full', 'queen', 'king'])
  })

  it('the Custom option is not selectable, so the picker cannot be set to nothing by the user', () => {
    setup({ ...SAMPLE_FORM, width: 150 })
    expect(screen.getByRole('option', { name: 'Custom room' })).toBeDisabled()
  })

  it('the blurb for a custom form falls back to a hint, so the description is never empty', () => {
    setup({ ...SAMPLE_FORM, width: 150 })
    expect(screen.getByLabelText('Start from an example')).toHaveAccessibleDescription(/Pick an example/)
  })
})

describe('bed card explanation', () => {
  it('shows the bed reason only on the bed card and joins it with a planner note', async () => {
    const plan = makePlan()
    const slots = plan.slots.map((s) => (s.role === 'bed' ? { ...s, note: 'on the other side of the door: it fits better there' } : s))
    mockApi(() => json(makeRecommend({ slots, bed_size: 'queen', bed_size_reason: 'Queen: the biggest size that fits this room' })))
    render(<App />)
    await screen.findByTestId('floorplan')
    fireEvent.click(find())
    await waitFor(() => expect(screen.getByTestId('slot-bed')).toHaveTextContent('Queen: the biggest size that fits this room. on the other side'))
    expect(screen.getByTestId('slot-dresser')).not.toHaveTextContent('biggest size')
  })
})
