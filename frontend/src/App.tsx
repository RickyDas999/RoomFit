import { useEffect, useState } from 'react'

export default function App() {
  const [health, setHealth] = useState('loading…')

  useEffect(() => {
    fetch('/api/health')
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status))
        return r.json()
      })
      .then((d: { status: string }) => setHealth(d.status))
      .catch(() => setHealth('backend unreachable'))
  }, [])

  return (
    <main>
      <h1>Room Fit</h1>
      <p>Backend health: {health}</p>
    </main>
  )
}
