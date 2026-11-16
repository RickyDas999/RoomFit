import { useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, evaluate, recommend } from './api/client'
import type { Candidate, EvaluateResponse, LayoutItem, Need, Product, RecommendResponse, Role, Room } from './api/types'
import { ROLES } from './api/types'
import { CoverageMeter, FlagsList, Verdict } from './components/Flags'
import { FloorPlan } from './components/FloorPlan'
import { RoomFormView } from './components/RoomForm'
import { SlotCard } from './components/SlotCard'
import { SAMPLE_FORM, toRoom, validate, type RoomForm } from './room'

/** What is on screen: one room, the checked plan for it, and the chosen products. */
interface View {
  room: Room
  plan: EvaluateResponse
  layout: LayoutItem[]
  rec: Pick<RecommendResponse, 'candidates' | 'searched' | 'sorted_by' | 'bed_size_reason'> | null
}

/** The bed is always wanted; the chair goes with the desk. */
const wanted = (role: Role, form: RoomForm) =>
  role === 'bed' || form.needs.includes(role === 'desk_chair' ? 'desk' : (role as Need))

const message = (e: unknown) => (e instanceof ApiError ? e.message : 'Something went wrong. Try again.')

export default function App() {
  const [form, setForm] = useState<RoomForm>(SAMPLE_FORM)
  const [view, setView] = useState<View | null>(null)
  const [busy, setBusy] = useState<'idle' | 'searching' | 'checking'>('idle')
  const [error, setError] = useState<string | null>(null)
  // True from an edit until the plan has been redrawn for the new room (the plan is dimmed meanwhile).
  const [dirty, setDirty] = useState(false)
  // Counts edits, so even an edit back to the same room redraws the plan.
  const [edits, setEdits] = useState(0)
  const latest = useRef(0) // only the newest request may update the screen

  const errors = useMemo(() => validate(form), [form])
  const room = useMemo(() => (errors.length === 0 ? toRoom(form) : null), [errors, form])
  const roomKey = room ? JSON.stringify(room) : ''

  // Draw the room (and its clearance zones) as the form changes. No catalog call.
  useEffect(() => {
    if (!room) return
    const id = window.setTimeout(async () => {
      const mine = ++latest.current
      try {
        const plan = await evaluate(room, [])
        if (mine !== latest.current) return
        setView({ room, plan, layout: [], rec: null })
        setError(null)
        setDirty(false)
      } catch (e) {
        if (mine === latest.current) setError(message(e))
      }
    }, 300)
    return () => window.clearTimeout(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- roomKey stands for room
  }, [roomKey, edits])

  const onChange = (next: RoomForm) => {
    latest.current++ // anything still in flight was for the old room: drop it
    setBusy('idle')
    setDirty(true)
    setEdits((n) => n + 1)
    setForm(next)
    setView((v) => (v ? { ...v, rec: null, layout: [] } : v)) // a new room needs a new search
  }

  async function findFurniture() {
    if (!room) return
    const mine = ++latest.current
    setBusy('searching')
    setError(null)
    try {
      const res = await recommend(room, form.bedSize)
      if (mine !== latest.current) return
      setView({
        room,
        plan: { slots: res.slots, placed: res.placed, evaluation: res.evaluation, zones: res.zones, unplaced: res.unplaced },
        layout: res.layout,
        rec: { candidates: res.candidates, searched: res.searched, sorted_by: res.sorted_by, bed_size_reason: res.bed_size_reason },
      })
      setDirty(false)
    } catch (e) {
      if (mine === latest.current) setError(message(e))
    } finally {
      if (mine === latest.current) setBusy('idle')
    }
  }

  async function swap(role: Role, product: Product) {
    if (!view) return
    const old = view.layout.find((i) => i.slot_id === role)
    const item: LayoutItem = { slot_id: role, product, footprint_basis: old?.footprint_basis ?? 'parsed' }
    const layout = [...view.layout.filter((i) => i.slot_id !== role), item]
    const mine = ++latest.current
    setBusy('checking')
    setError(null)
    try {
      const plan = await evaluate(view.room, layout)
      if (mine !== latest.current) return
      // a swapped bed is no longer "the size we chose", so drop that explanation
      const rec = role === 'bed' && view.rec ? { ...view.rec, bed_size_reason: null } : view.rec
      setView({ ...view, plan, layout, rec })
    } catch (e) {
      if (mine === latest.current) setError(message(e))
    } finally {
      if (mine === latest.current) setBusy('idle')
    }
  }

  const stale = dirty || busy !== 'idle'
  const candidates = (role: Role): Candidate[] => view?.rec?.candidates[role] ?? []

  return (
    <div className="app">
      <header className="app__header">
        <h1>Room Fit</h1>
        <p>Enter a room and get real products that fit together in it, with space to walk.</p>
      </header>

      <main className="app__grid">
        <section className="panel panel--form" aria-label="Room">
          <RoomFormView
            form={form}
            errors={errors}
            busy={busy === 'searching'}
            onChange={onChange}
            onReset={() => onChange(SAMPLE_FORM)}
            onSubmit={findFurniture}
          />
        </section>

        <section className="panel panel--plan" aria-label="Floor plan">
          <div role="status" className="status" aria-live="polite">
            {busy === 'searching' && 'Searching the Shopify catalog for each piece. This takes a few seconds…'}
            {busy === 'checking' && 'Checking the new layout…'}
          </div>
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          {view ? (
            <>
              <FloorPlan room={view.room} plan={view.plan} stale={stale} />
              {view.rec && <p className="sorted">Sorted by: {view.rec.sorted_by}</p>}
              <Verdict evaluation={view.plan.evaluation} />
              <CoverageMeter evaluation={view.plan.evaluation} />
              <FlagsList plan={view.plan} />
            </>
          ) : (
            !error && <p className="hint">Drawing your room…</p>
          )}
        </section>

        <section className="panel panel--slots" aria-label="Furniture">
          <h2>Furniture</h2>
          {view?.rec === null && view.layout.length === 0 && <p className="hint">Press “Find furniture that fits” to search for real products.</p>}
          {view &&
            ROLES.filter((r) => wanted(r, form)).map((role) => {
              const slot = view.plan.slots.find((s) => s.role === role)
              if (!slot) return null
              return (
                <SlotCard
                  key={role}
                  slot={slot}
                  item={view.layout.find((i) => i.slot_id === role)}
                  unplacedReason={view.plan.unplaced.find((u) => u.slot_id === role)?.reason}
                  explain={role === 'bed' ? view.rec?.bed_size_reason : null}
                  candidates={candidates(role)}
                  busy={busy !== 'idle'}
                  onSwap={(p) => swap(role, p)}
                />
              )
            })}
        </section>
      </main>
    </div>
  )
}
