import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { CoverageMeter, FlagsList, Verdict } from './Flags'
import { BROKEN_CHAIR_PLAN, makePlan } from '../testFixtures'
import type { Evaluation } from '../api/types'

afterEach(cleanup)

const ev = (over: Partial<Evaluation> = {}): Evaluation => ({
  hard_fails: [],
  coverage_pct: 20,
  coverage_status: 'ok',
  missing_needs: [],
  verdict: 'fits',
  ...over,
})

describe('FlagsList', () => {
  it('says so when there are no problems', () => {
    render(<FlagsList plan={makePlan()} />)
    expect(screen.getByText('No problems found.')).toBeInTheDocument()
    expect(screen.queryByRole('list')).toBeNull()
  })

  it('shows each broken rule with the inches short', () => {
    render(<FlagsList plan={BROKEN_CHAIR_PLAN()} />)
    expect(screen.getByText('Behind the desk chair: 6 in short')).toBeInTheDocument()
  })

  it('lists several hard fails, one per item', () => {
    const plan = makePlan({
      evaluation: ev({
        verdict: 'cramped',
        hard_fails: [
          { rule: 'path_from_door', pieces: ['dresser'], short_in: 6, message: 'clear path from the door: 6 in short' },
          { rule: 'bed_open_side', pieces: ['bed'], short_in: 12, message: 'open side of the bed: 12 in short' },
        ],
      }),
    })
    render(<FlagsList plan={plan} />)
    expect(screen.getAllByRole('listitem').map((li) => li.textContent)).toEqual([
      'Clear path from the door: 6 in short',
      'Open side of the bed: 12 in short',
    ])
  })

  it('explains each missing need in plain words', () => {
    render(<FlagsList plan={makePlan({ evaluation: ev({ verdict: 'incomplete', missing_needs: ['sleep', 'study', 'storage'] }) })} />)
    expect(screen.getByText('Sleep: no bed yet')).toBeInTheDocument()
    expect(screen.getByText('Study: no desk and chair yet')).toBeInTheDocument()
    expect(screen.getByText('Storage: no dresser or closet yet')).toBeInTheDocument()
  })

  it('shows coverage warnings and flags, but nothing at "ok"', () => {
    const { rerender } = render(<FlagsList plan={makePlan({ evaluation: ev({ coverage_pct: 41, coverage_status: 'warn' }) })} />)
    expect(screen.getByText(/Getting full: 41% .*warning above 40%/)).toBeInTheDocument()
    rerender(<FlagsList plan={makePlan({ evaluation: ev({ coverage_pct: 46, coverage_status: 'flag' }) })} />)
    expect(screen.getByText(/Too full: 46% .*flag above 45%/)).toBeInTheDocument()
    rerender(<FlagsList plan={makePlan()} />)
    expect(screen.queryByText(/full/)).toBeNull()
  })

  it('shows products that could not be placed, with the reason', () => {
    const plan = makePlan({ unplaced: [{ slot_id: 'desk', reason: 'dimensions missing' }, { slot_id: 'dresser', reason: 'no dresser fits under these rules' }] })
    render(<FlagsList plan={plan} />)
    expect(screen.getByText('Desk: dimensions missing')).toBeInTheDocument()
    expect(screen.getByText('Dresser: no dresser fits under these rules')).toBeInTheDocument()
  })

  it('announces changes politely to screen readers', () => {
    const { container } = render(<FlagsList plan={makePlan()} />)
    expect(container.querySelector('[aria-live="polite"]')).not.toBeNull()
  })
})

describe('CoverageMeter', () => {
  it.each([
    ['ok', 25, 'OK'],
    ['warn', 42, 'Warning: over 40%'],
    ['flag', 47, 'Flag: over 45%'],
  ] as const)('%s: says the status in words, not only colour', (status, pct, words) => {
    render(<CoverageMeter evaluation={ev({ coverage_pct: pct, coverage_status: status })} />)
    expect(screen.getByText(words)).toBeInTheDocument()
    const meter = screen.getByRole('meter')
    expect(meter).toHaveAttribute('aria-valuenow', String(pct))
    expect(meter).toHaveAttribute('aria-valuetext', `${pct}%, ${words}`)
  })

  it('shows the marks at 40% and 45% on a 0 to 60 scale', () => {
    const { container } = render(<CoverageMeter evaluation={ev()} />)
    const ticks = [...container.querySelectorAll<HTMLElement>('.meter__tick')].map((t) => parseFloat(t.style.left))
    expect(ticks[0]).toBeCloseTo((40 / 60) * 100, 3)
    expect(ticks[1]).toBeCloseTo(75, 3)
  })

  it('fills in proportion and never overflows the bar', () => {
    const { container, rerender } = render(<CoverageMeter evaluation={ev({ coverage_pct: 30 })} />)
    expect(container.querySelector<HTMLElement>('.meter__fill')!.style.width).toBe('50%')
    rerender(<CoverageMeter evaluation={ev({ coverage_pct: 95, coverage_status: 'flag' })} />)
    expect(container.querySelector<HTMLElement>('.meter__fill')!.style.width).toBe('100%')
    expect(screen.getByRole('meter')).toHaveAttribute('aria-valuenow', '60')
  })
})

describe('Verdict', () => {
  it.each([
    ['fits', 'Fits'],
    ['cramped', 'Cramped'],
    ['incomplete', 'Incomplete'],
  ] as const)('%s', (verdict, label) => {
    render(<Verdict evaluation={ev({ verdict })} />)
    expect(screen.getByText(label)).toBeInTheDocument()
  })
})
