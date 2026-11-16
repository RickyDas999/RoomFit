import type { CartSession } from '../api/types'
import { formatMoney, safeUrl } from '../format'

interface Props {
  /** There is something chosen to put in carts. */
  canCreate: boolean
  sessions: CartSession[] | null
  busy: 'idle' | 'creating' | 'cancelling'
  error: string | null
  onCreate: () => void
  onCancel: () => void
}

function Session({ s }: { s: CartSession }) {
  const total = s.totals.find((t) => t.type === 'total')
  const href = safeUrl(s.continue_url)
  return (
    <li className="cart" data-testid={`cart-${s.shop.domain}`}>
      <header>
        <h4>{s.shop.name || s.shop.domain}</h4>
        <span className={s.status === 'created' ? 'badge badge--ok' : 'badge badge--nofit'}>{s.status === 'created' ? 'cart created' : 'no cart'}</span>
      </header>
      {s.status === 'error' && <p className="slot__note">{s.error ?? 'The shop did not make a cart.'}</p>}
      {s.lines.length > 0 && (
        <ul className="cart__lines">
          {s.lines.map((l, i) => (
            <li key={i}>
              {l.quantity} × {l.title}
              {l.amount != null && <span className="hint"> {formatMoney(l.amount, s.currency)}</span>}
            </li>
          ))}
        </ul>
      )}
      {total && (
        <p className="cart__total">
          {total.display_text || 'Total'}: <strong>{formatMoney(total.amount, s.currency)}</strong>
        </p>
      )}
      {s.messages.map((m, i) => (
        <p key={i} className="hint">
          {m.content || m.code}
        </p>
      ))}
      {href && (
        <p>
          <a href={href} target="_blank" rel="noreferrer">
            Continue on merchant site
          </a>
        </p>
      )}
    </li>
  )
}

export function CheckoutPanel({ canCreate, sessions, busy, error, onCreate, onCancel }: Props) {
  const made = sessions?.filter((s) => s.status === 'created').length ?? 0
  return (
    <section className="panel panel--checkout" aria-labelledby="checkout-title">
      <h2 id="checkout-title">Checkout</h2>
      <p className="notice" role="note">
        <strong>Prototype: purchase disabled.</strong> This makes one cart per shop and shows what the shop returned. The app never takes payment or buys anything. Carts are cancelled when you change the room or leave the page.
      </p>
      <div className="actions">
        <button type="button" className="primary" onClick={onCreate} disabled={!canCreate || busy !== 'idle' || sessions !== null}>
          {busy === 'creating' ? 'Making carts…' : 'Make a cart at each shop'}
        </button>
        <button type="button" onClick={onCancel} disabled={made === 0 || busy !== 'idle'}>
          {busy === 'cancelling' ? 'Cancelling…' : 'Cancel carts'}
        </button>
      </div>
      <p aria-live="polite" className="status">
        {busy === 'creating' && 'Asking each shop for a cart…'}
        {busy === 'cancelling' && 'Cancelling the carts…'}
        {busy === 'idle' && sessions !== null && sessions.length > 0 && `${made} of ${sessions.length} carts made.`}
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {sessions && sessions.length === 0 && <p className="hint">Nothing chosen yet.</p>}
      {sessions && sessions.length > 0 && <ul className="carts">{sessions.map((s, i) => <Session key={`${s.shop.domain}-${i}`} s={s} />)}</ul>}
    </section>
  )
}
