import type { EvaluateResponse, LayoutItem, RecommendResponse, Room } from './types'

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
  return (await res.json()) as T
}

/** Re-check a layout (used for the room preview and after a swap). Does not touch the catalog. */
export function evaluate(room: Room, layout: LayoutItem[]): Promise<EvaluateResponse> {
  return post('/api/evaluate', { room, layout })
}

/** Search the catalog for each slot and pick the cheapest set that fits. Takes a few seconds. */
export function recommend(room: Room): Promise<RecommendResponse> {
  return post('/api/recommend', { room })
}
