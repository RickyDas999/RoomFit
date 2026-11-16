import type { Candidate, EvaluateResponse, LayoutItem, Product, RecommendResponse, Role, Slot, Zone } from './api/types'
import { ROLES } from './api/types'

/** Synthetic listings and plans shaped like API responses (made up, not Shopify data). */
export function makeProduct(id: string, over: Partial<Product> = {}): Product {
  return {
    id: `gid://shopify/p/${id}`,
    variant_id: `gid://shopify/ProductVariant/${id}`,
    title: `Item ${id}`,
    shop: { id: 'shop-1', name: 'Test Shop', domain: 'shop.example' },
    price: { amount: 8999, currency: 'USD' },
    image_url: null,
    url: `https://shop.example/products/${id}`,
    native_checkout: true,
    description: '',
    dimensions: { w: 48, d: 24, h: 30 },
    dimension_source: '48" x 24" x 30"',
    dimension_status: 'parsed',
    dimension_reason: null,
    dimension_confidence: 'stated',
    ...over,
  }
}

export const missing = (id: string, reason: Product['dimension_reason'] = 'no_dimensions'): Product =>
  makeProduct(id, { dimensions: null, dimension_source: null, dimension_status: 'missing', dimension_reason: reason, dimension_confidence: 'missing' })

export function makeSlots(over: Partial<Record<Role, Partial<Slot>>> = {}): Slot[] {
  return ROLES.map((role) => ({
    id: role,
    role,
    region: { x: 0, y: 0, w: 50, d: 50 },
    max_footprint: role === 'desk_chair' ? [20, 20] : [96, 54],
    fits: true,
    assumed_footprint: role === 'desk_chair',
    note: null,
    ...over[role],
  }))
}

export const zone = (rule: Zone['rule'], broken = false, short_in = 0, rect = { x: 10, y: 10, w: 24, d: 40 }): Zone => ({
  rule,
  rect,
  broken,
  short_in,
})

export function makePlan(over: Partial<EvaluateResponse> = {}): EvaluateResponse {
  return {
    slots: makeSlots(),
    placed: {
      bed: { x: 104, y: 112, w: 40, d: 80 },
      desk: { x: 0, y: 144, w: 24, d: 48 },
      desk_chair: { x: 24, y: 158, w: 20, d: 20 },
    },
    evaluation: { hard_fails: [], coverage_pct: 20.8, coverage_status: 'ok', missing_needs: [], verdict: 'fits' },
    zones: [zone('path_from_door', false, 0, { x: 54, y: 0, w: 36, d: 96 }), zone('behind_desk_chair')],
    unplaced: [],
    rotated: [],
    ...over,
  }
}

export const BROKEN_CHAIR_PLAN = (): EvaluateResponse =>
  makePlan({
    evaluation: {
      hard_fails: [{ rule: 'behind_desk_chair', pieces: ['desk_chair', 'desk'], short_in: 6, message: 'behind the desk chair: 6 in short' }],
      coverage_pct: 30,
      coverage_status: 'ok',
      missing_needs: [],
      verdict: 'cramped',
    },
    zones: [zone('path_from_door'), zone('behind_desk_chair', true, 6)],
  })

export const SMALL_DESK = makeProduct('desk-small', { title: 'Small desk', price: { amount: 4000, currency: 'USD' }, dimensions: { w: 48, d: 24, h: 30 } })
export const BIG_DESK = makeProduct('desk-big', {
  title: 'Big corner desk',
  price: { amount: 30000, currency: 'USD' },
  dimensions: { w: 72, d: 72, h: 30 },
  dimension_source: '72" x 72" x 30"',
})
export const NO_SIZE_DESK = missing('desk-nosize')

export const cand = (product: Product, fits_slot = true): Candidate => ({ product, fits_slot })

export function makeRecommend(over: Partial<RecommendResponse> = {}): RecommendResponse {
  const layout: LayoutItem[] = [
    { slot_id: 'bed', product: makeProduct('bed1', { title: 'Twin XL bed', dimensions: { w: 40, d: 80, h: null } }), footprint_basis: 'parsed' },
    { slot_id: 'desk', product: SMALL_DESK, footprint_basis: 'parsed' },
    { slot_id: 'desk_chair', product: missing('chair1'), footprint_basis: 'assumed' },
  ]
  const empty = (): Candidate[] => []
  return {
    ...makePlan(),
    layout,
    sorted_by: 'lowest price that fits',
    searched: {},
    candidates: {
      bed: [cand(layout[0].product)],
      desk: [cand(NO_SIZE_DESK, false), cand(SMALL_DESK), cand(BIG_DESK, false)],
      desk_chair: [cand(layout[2].product)],
      dresser: empty(),
      nightstand: empty(),
    },
    ...over,
  }
}
