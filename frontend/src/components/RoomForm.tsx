import { WALLS, wallLength, type RoomForm, DOOR_WIDTH, WINDOW_WIDTH } from '../room'
import type { Wall } from '../api/types'

interface Props {
  form: RoomForm
  errors: string[]
  busy: boolean
  onChange: (form: RoomForm) => void
  onReset: () => void
  onSubmit: () => void
}

const num = (v: string) => (v === '' ? Number.NaN : Number(v))

function WallChoice({ legend, name, value, onChange }: { legend: string; name: string; value: Wall; onChange: (w: Wall) => void }) {
  return (
    <fieldset className="field-group">
      <legend>{legend}</legend>
      <div className="choices">
        {WALLS.map((w) => (
          <label key={w} className="choice">
            <input type="radio" name={name} value={w} checked={value === w} onChange={() => onChange(w)} />
            {w}
          </label>
        ))}
      </div>
    </fieldset>
  )
}

export function RoomFormView({ form, errors, busy, onChange, onReset, onSubmit }: Props) {
  const set = <K extends keyof RoomForm>(key: K, value: RoomForm[K]) => onChange({ ...form, [key]: value })
  const bad = errors.length > 0
  return (
    <form
      aria-labelledby="room-form-title"
      onSubmit={(e) => {
        e.preventDefault()
        if (!bad && !busy) onSubmit()
      }}
    >
      <h2 id="room-form-title">Your room</h2>
      <p className="hint">All lengths are in inches. 12 ft is 144 in.</p>

      <div className="row">
        <div className="field">
          <label htmlFor="width">Width (in)</label>
          <input id="width" name="width" type="number" inputMode="numeric" min={1} step={1} value={Number.isNaN(form.width) ? '' : form.width} onChange={(e) => set('width', num(e.target.value))} required />
        </div>
        <div className="field">
          <label htmlFor="depth">Depth (in)</label>
          <input id="depth" name="depth" type="number" inputMode="numeric" min={1} step={1} value={Number.isNaN(form.depth) ? '' : form.depth} onChange={(e) => set('depth', num(e.target.value))} required />
        </div>
      </div>

      <WallChoice legend="Door wall" name="door-wall" value={form.doorWall} onChange={(w) => set('doorWall', w)} />
      <div className="field">
        <label htmlFor="door-offset">Door position (in from the start of that wall)</label>
        <input id="door-offset" name="door-offset" type="number" inputMode="numeric" min={0} max={Math.max(0, wallLength(form, form.doorWall) - DOOR_WIDTH)} step={1} value={Number.isNaN(form.doorOffset) ? '' : form.doorOffset} aria-describedby="door-hint" onChange={(e) => set('doorOffset', num(e.target.value))} required />
        <span id="door-hint" className="hint">{DOOR_WIDTH} in door, opens into the room. Walls start at the top-left corner.</span>
      </div>

      <WallChoice legend="Window wall" name="window-wall" value={form.windowWall} onChange={(w) => set('windowWall', w)} />
      <div className="field">
        <label htmlFor="window-offset">Window position (in from the start of that wall)</label>
        <input id="window-offset" name="window-offset" type="number" inputMode="numeric" min={0} max={Math.max(0, wallLength(form, form.windowWall) - WINDOW_WIDTH)} step={1} value={Number.isNaN(form.windowOffset) ? '' : form.windowOffset} aria-describedby="window-hint" onChange={(e) => set('windowOffset', num(e.target.value))} required />
        <span id="window-hint" className="hint">{WINDOW_WIDTH} in window.</span>
      </div>

      <div className="field">
        <label className="choice">
          <input type="checkbox" name="closet" checked={form.closet} onChange={(e) => set('closet', e.target.checked)} />
          Closet (48 x 24 in, in the corner at the start of the door wall)
        </label>
      </div>

      {bad && (
        <div role="alert" className="errors">
          {errors.map((e) => (
            <p key={e}>{e}</p>
          ))}
        </div>
      )}

      <div className="actions">
        <button type="submit" className="primary" disabled={bad || busy}>
          {busy ? 'Searching…' : 'Find furniture that fits'}
        </button>
        <button type="button" onClick={onReset} disabled={busy}>
          Use the sample room
        </button>
      </div>
    </form>
  )
}
