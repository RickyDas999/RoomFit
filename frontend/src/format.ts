import type { Product } from './api/types'

const trim = (n: number) => String(Math.round(n * 10) / 10)

export function formatPrice(p: Product): string {
  try {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: p.price.currency }).format(p.price.amount / 100)
  } catch {
    return `${(p.price.amount / 100).toFixed(2)} ${p.price.currency}`
  }
}

/** "48 x 24 x 30 in" (height only when the listing gives one). */
export function formatDimensions(d: NonNullable<Product['dimensions']>): string {
  const parts = [d.w, d.d, ...(d.h ? [d.h] : [])].map(trim)
  return `${parts.join(' × ')} in`
}

const REASON_TEXT: Record<string, string> = {
  no_dimensions: 'the description gives no size',
  no_unit: 'a size with no unit',
  shipping_size: 'only a shipping or box size',
  mattress_size: 'only a mattress size',
  component_only: 'only the size of a part',
  range: 'only a range',
  incomplete: 'only one measurement',
  multiple_sizes: 'several sizes listed',
  conflicting_labels: 'conflicting labels',
  implausible: 'a size that does not look like furniture',
  quantity: 'a quantity, not a size',
  too_many_values: 'too many numbers',
  size_mismatch: 'the listed size is smaller than the bed size in its name',
}

export function reasonText(reason: string | null | undefined): string {
  return (reason && Object.hasOwn(REASON_TEXT, reason) ? REASON_TEXT[reason] : undefined) ?? 'the description gives no size'
}

/** Only link to https pages. */
export function safeUrl(url: string | null | undefined): string | null {
  if (!url) return null
  try {
    const u = new URL(url)
    return u.protocol === 'https:' && !u.username && !u.password ? url : null
  } catch {
    return null
  }
}

const PLURAL: Record<string, string> = { bed: 'beds', desk: 'desks', dresser: 'dressers', nightstand: 'nightstands' }

/** "Of 25 desks Shopify returned, 9 list usable dimensions (6 stated, 3 inferred)." */
export function dataGapText(role: string, s: { found: number; with_dimensions: number; stated?: number; inferred?: number }): string {
  const what = Object.hasOwn(PLURAL, role) ? PLURAL[role] : 'products'
  const how = s.inferred ? ` (${s.stated ?? 0} stated, ${s.inferred} inferred)` : ''
  return `Of ${s.found} ${what} Shopify returned, ${s.with_dimensions} list usable dimensions${how}.`
}

/** Minor units (cents) to "$53.00". Currencies without cents (JPY) divide by 1. */
export function formatMoney(amount: number, currency: string | null | undefined): string {
  const cur = currency ?? 'USD'
  try {
    const f = new Intl.NumberFormat('en-US', { style: 'currency', currency: cur })
    return f.format(amount / 10 ** f.resolvedOptions().maximumFractionDigits!)
  } catch {
    return `${(amount / 100).toFixed(2)} ${cur}`
  }
}
