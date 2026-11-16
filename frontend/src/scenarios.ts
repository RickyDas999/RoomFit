import { SAMPLE_FORM, type RoomForm } from './room'

/** Preset rooms that show how the result changes as the room or the needs change. */
export interface Scenario {
  id: string
  label: string
  blurb: string
  form: RoomForm
}

const base = SAMPLE_FORM

export const SCENARIOS: Scenario[] = [
  {
    id: 'starter',
    label: 'Starter bedroom',
    blurb: '12 x 16 ft with a closet. A Twin XL bed, a dresser, a desk and a nightstand.',
    form: base,
  },
  {
    id: 'corner-door',
    label: 'Door in the corner',
    blurb: 'Same size, but the door moves to the far end of the wall. The bed goes to the open side and the desk moves to the door wall.',
    form: { ...base, doorOffset: 108, closet: false, windowOffset: 48 },
  },
  {
    id: 'small',
    label: 'Small room',
    blurb: '10 x 14 ft. No desk needed. A Twin XL bed is the biggest that fits.',
    form: { ...base, width: 120, depth: 168, doorOffset: 44, windowOffset: 36, closet: false, needs: ['nightstand', 'dresser'] },
  },
  {
    id: 'wfh',
    label: 'Work from home',
    blurb: 'A bigger room (14.7 x 16 ft) with a desk you need. The bed grows from a Twin XL to a queen.',
    form: { ...base, width: 176, depth: 192, doorOffset: 72 },
  },
  {
    id: 'studio',
    label: 'Studio, long and narrow',
    blurb: '10 x 18 ft, long and narrow. Everything fits, but a Twin XL is the biggest bed that does.',
    form: { ...base, width: 120, depth: 216, doorOffset: 44, windowOffset: 36, closet: false },
  },
  {
    id: 'studio-no-desk',
    label: 'Studio without a desk',
    blurb: 'The same studio with no desk wanted: fewer pieces, and more floor left over.',
    form: { ...base, width: 120, depth: 216, doorOffset: 44, windowOffset: 36, closet: false, needs: ['nightstand', 'dresser'] },
  },
]

/** The preset whose values equal the form, if any (so the picker can show it as selected). */
export function matchScenario(form: RoomForm): Scenario | undefined {
  const key = (f: RoomForm) => JSON.stringify({ ...f, needs: [...f.needs].sort() })
  return SCENARIOS.find((s) => key(s.form) === key(form))
}
