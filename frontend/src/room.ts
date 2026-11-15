import type { Room, Wall } from './api/types'

/** The room form works in inches, like the API. */
export interface RoomForm {
  width: number
  depth: number
  doorWall: Wall
  doorOffset: number
  windowWall: Wall
  windowOffset: number
  closet: boolean
}

export const DOOR_WIDTH = 32
export const WINDOW_WIDTH = 48
export const CLOSET_WIDTH = 48 // along the wall
export const CLOSET_DEPTH = 24 // into the room

/** Ricky's demo room: 12 x 16 ft, door centered on the top wall, window opposite, closet. */
export const SAMPLE_FORM: RoomForm = {
  width: 144,
  depth: 192,
  doorWall: 'top',
  doorOffset: 56,
  windowWall: 'bottom',
  windowOffset: 48,
  closet: true,
}

export const WALLS: Wall[] = ['top', 'bottom', 'left', 'right']

export function wallLength(form: Pick<RoomForm, 'width' | 'depth'>, wall: Wall): number {
  return wall === 'top' || wall === 'bottom' ? form.width : form.depth
}

/** Closet in the corner at the start of the door wall (Ricky, Nov 16). */
function closetRect(form: RoomForm) {
  const { width: W, depth: D } = form
  const c = CLOSET_WIDTH
  const d = CLOSET_DEPTH
  switch (form.doorWall) {
    case 'top':
      return { x: 0, y: 0, w: c, d }
    case 'bottom':
      return { x: 0, y: D - d, w: c, d }
    case 'left':
      return { x: 0, y: 0, w: d, d: c }
    case 'right':
      return { x: W - d, y: 0, w: d, d: c }
  }
}

export function toRoom(form: RoomForm): Room {
  return {
    width: form.width,
    depth: form.depth,
    door: { wall: form.doorWall, offset: form.doorOffset, width: DOOR_WIDTH, swing: 'in' },
    window: { wall: form.windowWall, offset: form.windowOffset, width: WINDOW_WIDTH },
    closet: form.closet ? closetRect(form) : null,
  }
}

/** Plain-language problems with the form, or an empty list if it can be sent. */
export function validate(form: RoomForm): string[] {
  const errors: string[] = []
  const finite = (n: number) => Number.isFinite(n)
  if (![form.width, form.depth, form.doorOffset, form.windowOffset].every(finite)) {
    return ['Fill in every number.']
  }
  if (form.width < 1 || form.depth < 1) errors.push('Width and depth must be at least 1 inch.')
  if (form.doorOffset < 0 || form.doorOffset + DOOR_WIDTH > wallLength(form, form.doorWall)) {
    errors.push(`The ${DOOR_WIDTH} in door does not fit on the ${form.doorWall} wall at that offset.`)
  }
  if (form.windowOffset < 0 || form.windowOffset + WINDOW_WIDTH > wallLength(form, form.windowWall)) {
    errors.push(`The ${WINDOW_WIDTH} in window does not fit on the ${form.windowWall} wall at that offset.`)
  }
  if (form.closet) {
    const room = toRoom(form)
    const c = room.closet
    if (c && (c.x + c.w > form.width || c.y + c.d > form.depth)) {
      errors.push('The closet does not fit in this room. Turn it off or make the room bigger.')
    }
  }
  return errors
}
