import type { BedChoice, CartSession, EvaluateResponse, LayoutItem, RecommendResponse, Room } from './types'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function post<T>(url: string, body: unknown): Promise<T> {
  let res: Response
  try {
    res = await fetch(url, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, 'Could not reach the Room Fit server. Is the backend running?')
  }
  if (!res.ok) {
    let message = `The server returned an error (${res.status}).`
    try {
      const data = (await res.json()) as { detail?: unknown }
      if (typeof data.detail === 'string') message = data.detail
      else if (res.status === 422) message = 'The server rejected the room. Check the numbers.'
    } catch {
      /* keep the generic message */
    }
    throw new ApiError(res.status, message)
  }
  try {
    return (await res.json()) as T
  } catch {
    throw new ApiError(res.status, 'The server sent a reply the app could not read.')
  }
}

/** Re-check a layout (used for the room preview and after a swap). Does not touch the catalog. */
export function evaluate(room: Room, layout: LayoutItem[]): Promise<EvaluateResponse> {
  return post('/api/evaluate', { room, layout })
}

/** Search the catalog for each slot and pick the cheapest set that fits. Takes a few seconds. */
export function recommend(room: Room, bedSize: BedChoice = 'auto'): Promise<RecommendResponse> {
  return post('/api/recommend', { room, bed_size: bedSize })
}

/** One cart per merchant for the chosen products. Nothing is bought. */
export async function createCarts(layout: LayoutItem[]): Promise<CartSession[]> {
  const res = await post<{ sessions: CartSession[] }>('/api/checkout', { layout })
  return res.sessions
}

export interface CartRef {
  domain: string
  cart_id: string
}

/** The carts that were really made (not the ones that failed). */
export const cartRefs = (sessions: CartSession[]): CartRef[] =>
  sessions.flatMap((s) => (s.status === 'created' && s.cart_id ? [{ domain: s.shop.domain, cart_id: s.cart_id }] : []))

export function cancelCarts(carts: CartRef[]): Promise<{ cancelled: number; failed: number }> {
  return post('/api/checkout/cancel', { carts })
}

/** Cancel carts as the page closes: sendBeacon survives the page going away. Best effort. */
export function cancelCartsOnExit(carts: CartRef[]): void {
  if (carts.length === 0 || typeof navigator === 'undefined' || !navigator.sendBeacon) return
  navigator.sendBeacon('/api/checkout/cancel', new Blob([JSON.stringify({ carts })], { type: 'application/json' }))
}
