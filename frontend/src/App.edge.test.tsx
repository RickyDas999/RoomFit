import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import App from './App'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const stubFetch = (f: unknown) => vi.stubGlobal('fetch', f)

test('shows loading state before fetch resolves and calls /api/health', () => {
  const f = vi.fn(() => new Promise(() => {}))
  stubFetch(f)
  render(<App />)
  expect(screen.getByText('Backend health: loading…')).toBeInTheDocument()
  expect(f).toHaveBeenCalledWith('/api/health')
})

test('shows unreachable when fetch rejects', async () => {
  stubFetch(vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
  render(<App />)
  expect(await screen.findByText('Backend health: backend unreachable')).toBeInTheDocument()
})

test('shows unreachable when body is not JSON', async () => {
  stubFetch(vi.fn().mockResolvedValue({ json: async () => { throw new SyntaxError('bad json') } }))
  render(<App />)
  expect(await screen.findByText('Backend health: backend unreachable')).toBeInTheDocument()
})

test('HTTP 500 with JSON error body is not shown as healthy', async () => {
  stubFetch(vi.fn().mockResolvedValue({ ok: false, status: 500, json: async () => ({ detail: 'boom' }) }))
  render(<App />)
  expect(await screen.findByText('Backend health: backend unreachable')).toBeInTheDocument()
})
