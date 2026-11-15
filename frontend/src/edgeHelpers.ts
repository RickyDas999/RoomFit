import type { Room } from './api/types'
import { SAMPLE_FORM, toRoom } from './room'
export const makeRoom = (): Room => toRoom(SAMPLE_FORM)
