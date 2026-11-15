import { describe, expect, it } from 'vitest'
import { reasonText } from './format'
import { ApiError, evaluate } from './api/client'
import { SAMPLE_FORM, toRoom } from './room'
import { vi } from 'vitest'

describe('reasonText', () => {
  it.each(['__proto__', 'constructor', 'toString', 'hasOwnProperty', 'valueOf'])('never returns a non-string for the key %s', (key) => {
    expect(reasonText(key)).toBe('the description gives no size')
  })
  it('still translates real reasons', () => {
    expect(reasonText('multiple_sizes')).toBe('several sizes listed')
  })
})

describe('api client', () => {
  it('turns a 200 with a body that is not JSON into an ApiError', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response('<html>oops</html>', { status: 200 }))))
    await expect(evaluate(toRoom(SAMPLE_FORM), [])).rejects.toBeInstanceOf(ApiError)
    vi.unstubAllGlobals()
  })
})
