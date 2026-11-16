/**
 * The merchant's website around the Room Planner: announcement bar, header, footer.
 * Everything here is for show (no links, no actions), so the prototype can be seen the way a
 * shopper would meet it inside a real store. The store name is a placeholder.
 */
export const STORE_NAME = 'Northfield Home'

const NAV = ['New in', 'Bedroom', 'Living', 'Office', 'Storage', 'Room Planner']

const icon = { width: 20, height: 20, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.6, strokeLinecap: 'round', strokeLinejoin: 'round' } as const

export function StoreHeader() {
  return (
    <>
      <div className="announce" aria-hidden="true">
        Free shipping on orders over $99
      </div>
      <header className="store-header" aria-hidden="true">
        <div className="store-header__inner">
          <p className="store-header__logo">{STORE_NAME}</p>
          <ul className="store-header__nav" aria-hidden="true">
            {NAV.map((n) => (
              <li key={n} className={n === 'Room Planner' ? 'is-current' : undefined}>
                {n}
              </li>
            ))}
          </ul>
          <div className="store-header__tools" aria-hidden="true">
            <svg {...icon}>
              <circle cx="11" cy="11" r="6.5" />
              <path d="m20 20-4.2-4.2" />
            </svg>
            <svg {...icon}>
              <circle cx="12" cy="8.5" r="3.5" />
              <path d="M5 20c.8-3.6 3.6-5.5 7-5.5s6.2 1.9 7 5.5" />
            </svg>
            <svg {...icon}>
              <path d="M5.5 8h13l-1 12h-11z" />
              <path d="M9 8V7a3 3 0 0 1 6 0v1" />
            </svg>
          </div>
        </div>
      </header>
    </>
  )
}

const FOOTER_COLUMNS: [string, string[]][] = [
  ['Shop', ['New arrivals', 'Bedroom', 'Living room', 'Home office', 'Storage']],
  ['Help', ['Delivery', 'Returns', 'Assembly guides', 'Contact us']],
  [STORE_NAME, ['Our story', 'Trade program', 'Careers']],
]

export function StoreFooter() {
  return (
    <footer className="store-footer" aria-hidden="true">
      <div className="store-footer__inner">
        {FOOTER_COLUMNS.map(([title, items]) => (
          <div key={title}>
            <p className="store-footer__title">{title}</p>
            <ul>
              {items.map((i) => (
                <li key={i}>{i}</li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <p className="store-footer__fine">{STORE_NAME} is a placeholder store. The Room Planner is the prototype; the menus and links around it are for show.</p>
    </footer>
  )
}
