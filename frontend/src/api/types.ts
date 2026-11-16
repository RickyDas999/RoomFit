import type { components } from './schema'

type S = components['schemas']

export type Room = S['Room']
export type Rect = S['Rect']
export type Slot = S['Slot']
export type Zone = S['Zone']
export type Product = S['Product']
export type LayoutItem = S['LayoutItem']
export type Candidate = S['Candidate']
export type Evaluation = S['Evaluation']
export type EvaluateResponse = S['EvaluateResponse']
export type RecommendResponse = S['RecommendResponse']
export type SearchStats = S['SearchStats']
export type Role = S['Slot']['role']
export type Wall = S['Door']['wall']
export type Need = NonNullable<Room['needs']>[number]
export type BedChoice = S['RecommendRequest']['bed_size'] & string

/** Slot order in the side panel (the order the engine plans them). */
export const ROLES: Role[] = ['bed', 'desk', 'desk_chair', 'dresser', 'nightstand']

export const ROLE_LABEL: Record<Role, string> = {
  bed: 'Bed',
  desk: 'Desk',
  desk_chair: 'Desk chair',
  dresser: 'Dresser',
  nightstand: 'Nightstand',
}
