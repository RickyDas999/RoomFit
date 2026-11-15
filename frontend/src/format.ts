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
}

export function reasonText(reason: string | null | undefined): string {
  return (reason && Object.hasOwn(REASON_TEXT, reason) ? REASON_TEXT[reason] : undefined) ?? 'the description gives no size'
}

/** Only link to https pages. */
export function safeUrl(url: string | null | undefined): string | null {
  if (!url) return null
  try {
    return new URL(url).protocol === 'https:' ? url : null
  } catch {
    return null
  }
}
