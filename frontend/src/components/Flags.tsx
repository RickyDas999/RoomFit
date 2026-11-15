import type { Evaluation, EvaluateResponse } from '../api/types'
import { ROLE_LABEL } from '../api/types'

const NEED_TEXT: Record<string, string> = {
  sleep: 'Sleep: no bed yet',
  study: 'Study: no desk and chair yet',
  storage: 'Storage: no dresser or closet yet',
}

const VERDICT: Record<Evaluation['verdict'], { label: string; hint: string }> = {
  fits: { label: 'Fits', hint: 'Everything is placed with comfortable walking space.' },
  cramped: { label: 'Cramped', hint: 'A clearance is broken, or the room is too full.' },
  incomplete: { label: 'Incomplete', hint: 'A basic need is missing.' },
}

const COVERAGE_TEXT = {
  ok: 'OK',
  warn: 'Warning: over 40%',
  flag: 'Flag: over 45%',
} as const

/** Scale of the coverage meter. Our soft limits are 40% and 45%. */
const METER_MAX = 60

export function Verdict({ evaluation }: { evaluation: Evaluation }) {
  const v = VERDICT[evaluation.verdict]
  return (
    <p className={`verdict verdict--${evaluation.verdict}`}>
      <strong>{v.label}</strong>
      <span>{v.hint}</span>
    </p>
  )
}

/** One decimal at most (the server sends two). */
const shown = (n: number) => Math.round(n * 10) / 10

export function CoverageMeter({ evaluation }: { evaluation: Evaluation }) {
  const pct = shown(evaluation.coverage_pct)
  const fill = Math.min(pct, METER_MAX) / METER_MAX
  return (
    <div className="coverage">
      <p id="coverage-label">
        Floor covered by furniture: <strong>{pct}%</strong>{' '}
        <span className={`coverage__status coverage__status--${evaluation.coverage_status}`}>
          {COVERAGE_TEXT[evaluation.coverage_status]}
        </span>
      </p>
      <div
        className="meter"
        role="meter"
        aria-labelledby="coverage-label"
        aria-valuemin={0}
        aria-valuemax={METER_MAX}
        aria-valuenow={Math.min(pct, METER_MAX)}
        aria-valuetext={`${pct}%, ${COVERAGE_TEXT[evaluation.coverage_status]}`}
      >
        <div className={`meter__fill meter__fill--${evaluation.coverage_status}`} style={{ width: `${fill * 100}%` }} />
        <span className="meter__tick" style={{ left: `${(40 / METER_MAX) * 100}%` }} aria-hidden="true" />
        <span className="meter__tick" style={{ left: `${(45 / METER_MAX) * 100}%` }} aria-hidden="true" />
      </div>
      <p className="hint">Marks at 40% (warn) and 45% (flag).</p>
    </div>
  )
}

/** Everything that is wrong with the layout, in plain words. */
export function FlagsList({ plan }: { plan: EvaluateResponse }) {
  const ev = plan.evaluation
  const items: { key: string; text: string; kind: 'hard' | 'need' | 'soft' | 'missing' }[] = []
  for (const f of ev.hard_fails) items.push({ key: `${f.rule}-${f.pieces.join('-')}`, text: capitalize(f.message), kind: 'hard' })
  if (ev.coverage_status !== 'ok') {
    items.push({
      key: 'coverage',
      text: ev.coverage_status === 'flag' ? `Too full: ${shown(ev.coverage_pct)}% of the floor is covered (flag above 45%)` : `Getting full: ${shown(ev.coverage_pct)}% of the floor is covered (warning above 40%)`,
      kind: 'soft',
    })
  }
  for (const need of ev.missing_needs) items.push({ key: `need-${need}`, text: NEED_TEXT[need] ?? `Missing: ${need}`, kind: 'need' })
  for (const u of plan.unplaced) items.push({ key: `unplaced-${u.slot_id}`, text: `${ROLE_LABEL[u.slot_id]}: ${u.reason}`, kind: 'missing' })

  return (
    <section aria-labelledby="flags-title" className="flags">
      <h3 id="flags-title">Flags</h3>
      <div aria-live="polite">
        {items.length === 0 ? (
          <p className="flags__none">No problems found.</p>
        ) : (
          <ul>
            {items.map((i) => (
              <li key={i.key} className={`flag flag--${i.kind}`}>
                {i.text}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1)
}
