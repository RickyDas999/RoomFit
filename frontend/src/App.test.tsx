import { render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import App from './App'

afterEach(() => vi.unstubAllGlobals())

test('shows the health response', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ json: async () => ({ status: 'ok' }) }))
  render(<App />)
  expect(await screen.findByText('Backend health: ok')).toBeInTheDocument()
})
