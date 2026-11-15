import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, evaluate } from './client'
import { makeRoom } from '../edgeHelpers'

const room = makeRoom()
const stub = (res: () => Promise<Response>) => vi.stubGlobal('fetch', vi.fn(res))
afterEach(() => vi.unstubAllGlobals())

describe('api client errors', () => {
  it('network failure -> status 0 friendly message', async () => {
    stub(() => Promise.reject(new TypeError('Failed to fetch')))
    await expect(evaluate(room, [])).rejects.toMatchObject({ status: 0, message: /Could not reach/ })
  })
  it('non-JSON error body keeps generic message with status', async () => {
    stub(() => Promise.resolve(new Response('<html>Bad Gateway</html>', { status: 502 })))
    await expect(evaluate(room, [])).rejects.toMatchObject({ status: 502, message: 'The server returned an error (502).' })
  })
  it('502 with string detail uses it', async () => {
    stub(() => Promise.resolve(new Response(JSON.stringify({ detail: 'Shopify is down' }), { status: 502 })))
    await expect(evaluate(room, [])).rejects.toMatchObject({ message: 'Shopify is down' })
  })
  it('422 with array detail gives the room message, not [object Object]', async () => {
    stub(() => Promise.resolve(new Response(JSON.stringify({ detail: [{ msg: 'x' }] }), { status: 422 })))
    await expect(evaluate(room, [])).rejects.toMatchObject({ status: 422, message: expect.stringMatching(/rejected the room/) })
  })
  it('error body that is JSON null does not crash with TypeError', async () => {
    stub(() => Promise.resolve(new Response('null', { status: 500 })))
    const e = await evaluate(room, []).catch((x) => x)
    expect(e).toBeInstanceOf(ApiError)
  })
  it('empty error body', async () => {
    stub(() => Promise.resolve(new Response('', { status: 500 })))
    await expect(evaluate(room, [])).rejects.toBeInstanceOf(ApiError)
  })
  it('200 with a non-JSON body surfaces as ApiError (App only shows friendly text for ApiError)', async () => {
    stub(() => Promise.resolve(new Response('not json', { status: 200 })))
    await expect(evaluate(room, [])).rejects.toBeInstanceOf(ApiError)
  })
})
