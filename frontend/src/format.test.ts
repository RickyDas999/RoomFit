import { describe, expect, it } from 'vitest'
import { formatDimensions, formatPrice, reasonText, safeUrl } from './format'
import { makeProduct } from './testFixtures'

const price = (amount: number, currency: string) => formatPrice(makeProduct('p', { price: { amount, currency } }))

describe('formatPrice', () => {
  it('basics', () => {
    expect(price(8999, 'USD')).toBe('$89.99')
    expect(price(0, 'USD')).toBe('$0.00')
    expect(price(1_000_000_00, 'USD')).toBe('$1,000,000.00')
  })
  it('odd currency codes never throw', () => {
    for (const c of ['', 'us', 'USDX', 'XXX', 'usd', '$$$', 'JPY', 'BHD']) expect(() => price(1000, c)).not.toThrow()
  })
  it('unknown code falls back to readable text', () => {
    expect(price(1000, 'ZZ')).toBe('10.00 ZZ')
  })
  it('JPY amounts are not divided wrongly (minor units: JPY has 0 decimals)', () => {
    // Shopify amount is in minor units /100 by contract here; just assert no crash and sensible output
    expect(price(150000, 'JPY')).toContain('1,500')
  })
  it('negative and NaN do not throw', () => {
    expect(price(-500, 'USD')).toContain('5.00')
    expect(() => price(Number.NaN, 'USD')).not.toThrow()
  })
})

describe('formatDimensions', () => {
  it('hides zero / null height', () => {
    expect(formatDimensions({ w: 48, d: 24, h: 0 })).toBe('48 × 24 in')
    expect(formatDimensions({ w: 48, d: 24, h: null })).toBe('48 × 24 in')
  })
  it('rounds long decimals', () => {
    expect(formatDimensions({ w: 47.123456, d: 23.96, h: 30.04 })).toBe('47.1 × 24 × 30 in')
  })
})

describe('reasonText', () => {
  it('unknown / empty reasons fall back', () => {
    for (const r of ['nope', '', null, undefined, '__proto__', 'constructor', 'toString']) {
      expect(reasonText(r as string)).toBe('the description gives no size')
    }
  })
})

describe('safeUrl', () => {
  it('allows https only', () => {
    expect(safeUrl('https://a.example/x')).toBe('https://a.example/x')
    expect(safeUrl('HTTPS://A.EXAMPLE/x')).not.toBeNull()
  })
  it.each(['javascript:alert(1)', 'JaVaScRiPt:alert(1)', 'data:text/html,<script>1</script>', '//evil.example', 'http://a.example', 'ftp://a', '', ' ', 'https//a', '\tjavascript:alert(1)', 'java\nscript:alert(1)', 'vbscript:x', 'blob:https://a.example/1', 'file:///etc/passwd'])(
    'rejects %j',
    (u) => expect(safeUrl(u)).toBeNull(),
  )
  it('very long url does not throw', () => {
    expect(() => safeUrl('https://a.example/' + 'a'.repeat(100000))).not.toThrow()
  })
})
