import { useId } from 'react'
import { doorGeometry, windowLines } from '../floorplan'
import type { EvaluateResponse, Rect, Room, Zone } from '../api/types'
import { ROLE_LABEL, type Role } from '../api/types'

const PAD = 14 // inches of margin around the room

const PIECE_LABEL: Record<string, string> = {
  bed: 'Bed',
  desk: 'Desk',
  desk_chair: 'Chair',
  dresser: 'Dresser',
  nightstand: 'Stand',
}

export const ZONE_LABEL: Record<Zone['rule'], string> = {
  path_from_door: 'Path from the door',
  bed_open_side: 'Open side of the bed',
  in_front_of_dresser: 'In front of the dresser',
  in_front_of_closet: 'In front of the closet',
  behind_desk_chair: 'Behind the desk chair',
}

const center = (r: Rect) => ({ x: r.x + r.w / 2, y: r.y + r.d / 2 })
const fmt = (n: number) => String(Math.round(n * 10) / 10)

interface Props {
  room: Room
  plan: EvaluateResponse
  /** True while the room has changed and the plan is being re-checked. */
  stale?: boolean
}

/** Top-down floor plan, drawn to scale (1 SVG unit = 1 inch). */
export function FloorPlan({ room, plan, stale = false }: Props) {
  const gridId = useId()
  const door = doorGeometry(room)
  const placed = Object.entries(plan.placed) as [Role, Rect][]
  const broken = plan.zones.filter((z) => z.broken)
  const summary =
    `Floor plan, ${fmt(room.width)} by ${fmt(room.depth)} inches. ` +
    (placed.length ? `Placed: ${placed.map(([r]) => ROLE_LABEL[r].toLowerCase()).join(', ')}. ` : 'No furniture placed yet. ') +
    (broken.length ? `Broken clearances: ${broken.map((z) => ZONE_LABEL[z.rule].toLowerCase()).join(', ')}.` : 'All clearances are met.')

  return (
    <figure className={stale ? 'plan plan--stale' : 'plan'}>
      <svg
        viewBox={`${-PAD} ${-PAD} ${room.width + PAD * 2} ${room.depth + PAD * 2}`}
        role="img"
        aria-label={summary}
        data-testid="floorplan"
      >
        <defs>
          <pattern id={gridId} width="12" height="12" patternUnits="userSpaceOnUse">
            <path d="M 12 0 L 0 0 0 12" className="plan__grid" />
          </pattern>
        </defs>

        <rect x={0} y={0} width={room.width} height={room.depth} className="plan__floor" />
        <rect x={0} y={0} width={room.width} height={room.depth} fill={`url(#${gridId})`} />

        {plan.zones.map((z) => (
          <g key={z.rule} data-testid={`zone-${z.rule}`} data-broken={z.broken}>
            <rect
              x={z.rect.x}
              y={z.rect.y}
              width={z.rect.w}
              height={z.rect.d}
              className={z.broken ? 'plan__zone plan__zone--broken' : 'plan__zone'}
            >
              <title>
                {ZONE_LABEL[z.rule]}
                {z.broken ? `: ${fmt(z.short_in)} in short` : ': clear'}
              </title>
            </rect>
          </g>
        ))}

        {room.closet && (
          <g data-testid="closet">
            <rect x={room.closet.x} y={room.closet.y} width={room.closet.w} height={room.closet.d} className="plan__closet" />
            <text {...center(room.closet)} className="plan__label" textAnchor="middle" dominantBaseline="middle">
              Closet
            </text>
          </g>
        )}

        {placed.map(([role, r]) => (
          <g key={role} data-testid={`piece-${role}`}>
            <rect
              x={r.x}
              y={r.y}
              width={r.w}
              height={r.d}
              className={role === 'desk_chair' ? 'plan__piece plan__piece--assumed' : 'plan__piece'}
            >
              <title>
                {ROLE_LABEL[role]}, {fmt(r.w)} x {fmt(r.d)} in{role === 'desk_chair' ? ' (assumed size)' : ''}
              </title>
            </rect>
            <text {...center(r)} className="plan__label" textAnchor="middle" dominantBaseline="middle">
              {PIECE_LABEL[role]}
            </text>
          </g>
        ))}

        {/* "N in short" labels sit above the furniture so nothing hides them */}
        {broken.map((z) => (
          <text key={z.rule} {...center(z.rect)} className="plan__zone-label" textAnchor="middle" data-testid={`zone-label-${z.rule}`}>
            {fmt(z.short_in)} in short
          </text>
        ))}

        {/* walls on top, with the door opening cut out of them */}
        <rect x={0} y={0} width={room.width} height={room.depth} className="plan__wall" />
        <line x1={door.start.x} y1={door.start.y} x2={door.end.x} y2={door.end.y} className="plan__opening" />
        <line x1={door.start.x} y1={door.start.y} x2={door.leafEnd.x} y2={door.leafEnd.y} className="plan__door" />
        <path d={door.arc} className="plan__swing" data-testid="door-swing" />
        {windowLines(room).map(([a, b], i) => (
          <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} className="plan__window" />
        ))}
      </svg>
      <figcaption className="plan__legend">
        <span className="swatch swatch--zone" aria-hidden="true" /> clearance
        <span className="swatch swatch--broken" aria-hidden="true" /> clearance broken
        <span className="swatch swatch--piece" aria-hidden="true" /> furniture
        <span className="swatch swatch--assumed" aria-hidden="true" /> assumed size
        <span className="plan__scale">grid squares are 12 in</span>
      </figcaption>
    </figure>
  )
}
