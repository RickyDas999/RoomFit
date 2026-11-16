import { useId, useState } from 'react'
import type { Candidate, LayoutItem, Product, SearchStats, Slot } from '../api/types'
import { ROLE_LABEL } from '../api/types'
import { dataGapText, formatDimensions, formatPrice, reasonText, safeUrl } from '../format'

interface Props {
  /** Why this size or place was chosen (e.g. "Queen: the biggest size that fits this room"). */
  explain?: string | null
  /** The piece is placed turned 90 degrees (short side along the wall). */
  rotated?: boolean
  /** How many of the searched listings had usable dimensions. */
  gap?: SearchStats
  slot: Slot
  item?: LayoutItem
  /** Why nothing is placed in this slot, if the server said. */
  unplacedReason?: string
  candidates: Candidate[]
  busy: boolean
  onSwap: (product: Product) => void
}

/** How far to trust a listing's size: stated, inferred (a guess), unclear or missing. */
function Confidence({ product }: { product: Product }) {
  const usable = product.dimensions && product.dimension_status === 'parsed'
  const unclear = <span className="badge badge--unclear">size unclear</span>
  if (!usable) {
    const bad = product.dimension_status === 'ambiguous' || product.dimension_confidence === 'ambiguous'
    return bad ? unclear : <span className="badge badge--missing">dimensions missing</span>
  }
  // only a size we know to be stated or inferred is shown as trusted; anything else is unclear
  if (product.dimension_confidence === 'stated') return <span className="badge badge--stated">stated</span>
  if (product.dimension_confidence === 'inferred') return <span className="badge badge--inferred">inferred</span>
  return unclear
}

function Dimensions({ product, assumed, slot }: { product: Product; assumed: boolean; slot: Slot }) {
  if (assumed) {
    return (
      <p className="dims">
        <span className="badge badge--assumed">assumed {slot.max_footprint[0]} × {slot.max_footprint[1]} in</span>{' '}
        <span className="hint">Chair listings rarely give a size, so the fit uses this.</span>
      </p>
    )
  }
  if (product.dimensions && product.dimension_status === 'parsed') {
    return (
      <p className="dims">
        <strong>{formatDimensions(product.dimensions)}</strong>
        {' '}
        <Confidence product={product} />
        {product.dimension_source && (
          <span className="hint">
            {' '}
            {product.dimension_confidence === 'inferred' ? 'guessed by Shopify from the product specs, so it may be wrong' : 'from the listing'}: “{product.dimension_source}”
          </span>
        )}
      </p>
    )
  }
  return (
    <p className="dims">
      <Confidence product={product} />{' '}
      <span className="hint">{reasonText(product.dimension_reason)}</span>
    </p>
  )
}

function ProductSummary({ product, assumed, slot }: { product: Product; assumed: boolean; slot: Slot }) {
  const href = safeUrl(product.url)
  return (
    <div className="product">
      {safeUrl(product.image_url) ? <img src={safeUrl(product.image_url) ?? undefined} alt="" width={72} height={72} loading="lazy" /> : <div className="product__noimg" aria-hidden="true" />}
      <div className="product__body">
        <p className="product__title">{href ? <a href={href} target="_blank" rel="noreferrer">{product.title}</a> : product.title}</p>
        <p className="product__meta">
          {product.shop.name} · <strong>{formatPrice(product)}</strong>
        </p>
        <Dimensions product={product} assumed={assumed} slot={slot} />
      </div>
    </div>
  )
}

/** The platform's data gap, in numbers, summed over every search. */
export function DataGap({ searched }: { searched: Partial<Record<string, SearchStats>> }) {
  const rows = Object.entries(searched).filter(([role, s]) => role !== 'desk_chair' && s)
  const found = rows.reduce((n, [, s]) => n + (s?.found ?? 0), 0)
  const usable = rows.reduce((n, [, s]) => n + (s?.with_dimensions ?? 0), 0)
  if (found === 0) return null
  return (
    <p className="datagap" data-testid="data-gap">
      Shopify returned {found} listings. Only {usable} list usable dimensions.
    </p>
  )
}

export function SlotCard({ slot, item, unplacedReason, candidates, busy, onSwap, explain, rotated, gap }: Props) {
  const [open, setOpen] = useState(false)
  const listId = useId()
  const label = ROLE_LABEL[slot.role]
  const assumed = item?.footprint_basis === 'assumed'
  return (
    <article className="slot" aria-label={label} data-testid={`slot-${slot.role}`}>
      <header>
        <h3>{label}</h3>
        {!slot.fits && <span className="badge badge--nofit">no space</span>}
      </header>

      {!slot.fits && <p className="slot__note">{slot.note ?? `no ${label.toLowerCase()} fits under these rules`}</p>}
      {slot.fits && (slot.note || explain) && <p className="slot__why">{[explain, slot.note].filter(Boolean).join('. ')}</p>}
      {slot.fits && !item && <p className="slot__note">{unplacedReason ?? 'Nothing chosen yet.'}</p>}
      {item && <ProductSummary product={item.product} assumed={assumed} slot={slot} />}
      {item && rotated && <p className="slot__why">Turned 90°: its short side runs along the wall, which is the way it fits.</p>}
      {gap && gap.found > 0 && slot.role !== 'desk_chair' && <p className="hint datagap">{dataGapText(slot.role, gap)}</p>}
      {item && unplacedReason && <p className="slot__note">{unplacedReason}</p>}

      {slot.fits && candidates.length > 0 && (
        <>
          <button type="button" className="link" aria-expanded={open} aria-controls={open ? listId : undefined} onClick={() => setOpen((o) => !o)}>
            {open ? 'Hide alternatives' : `Swap (${candidates.length} found)`}
          </button>
          {open && (
            <ul id={listId} className="candidates">
              {candidates.map((c) => {
                const selected = c.product.id === item?.product.id
                return (
                  <li key={c.product.id} className={selected ? 'candidate candidate--selected' : 'candidate'}>
                    <div>
                      <p className="product__title">{c.product.title}</p>
                      <p className="product__meta">
                        {c.product.shop.name} · <strong>{formatPrice(c.product)}</strong>
                      </p>
                      {slot.role === 'desk_chair' ? null : (
                        <p className="dims">
                          {c.product.dimensions && c.product.dimension_status === 'parsed' ? (
                            <>
                              <strong>{formatDimensions(c.product.dimensions)}</strong> <Confidence product={c.product} />
                            </>
                          ) : (
                            <Confidence product={c.product} />
                          )}{' '}
                          {c.product.dimensions && !c.fits_slot && <span className="badge badge--nofit">bigger than the space</span>}
                        </p>
                      )}
                    </div>
                    <button
                      type="button"
                      disabled={selected || busy}
                      aria-label={selected ? `${c.product.title} is selected` : `Use ${c.product.title} as the ${label.toLowerCase()}`}
                      onClick={() => onSwap(c.product)}
                    >
                      {selected ? 'Selected' : 'Use this'}
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </>
      )}
    </article>
  )
}
