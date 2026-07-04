import { useEffect, useRef, useState } from 'react'

// Not in the originally requested hooks list, but coding_rules.md explicitly
// requires "WebSocket connection managed in a single useWebSocket hook" —
// AlertBanner.jsx uses this rather than opening a socket itself.
//
// Note: as of this build, the backend has no /api/v1/ws/alerts route
// implemented yet (layer1_design.md documents it, but it was never wired up
// in the FastAPI skeleton). This hook is written against that documented
// contract and degrades gracefully — it will show "disconnected" and retry
// on a timer — until that route exists.
const RECONNECT_DELAY_MS = 5000
const MAX_MESSAGES = 20

export function useWebSocket(path) {
  const [messages, setMessages] = useState([])
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState(null)
  const socketRef = useRef(null)
  const reconnectTimerRef = useRef(null)

  useEffect(() => {
    let cancelled = false

    function connect() {
      const base = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(
        /^http/,
        'ws',
      )
      const socket = new WebSocket(`${base}${path}`)
      socketRef.current = socket

      socket.onopen = () => {
        if (cancelled) return
        setConnected(true)
        setError(null)
      }

      socket.onmessage = (event) => {
        if (cancelled) return
        try {
          const data = JSON.parse(event.data)
          setMessages((prev) => [data, ...prev].slice(0, MAX_MESSAGES))
        } catch {
          setMessages((prev) => [{ message: event.data }, ...prev].slice(0, MAX_MESSAGES))
        }
      }

      socket.onerror = () => {
        if (cancelled) return
        setError('Alert stream unavailable')
      }

      socket.onclose = () => {
        if (cancelled) return
        setConnected(false)
        reconnectTimerRef.current = setTimeout(connect, RECONNECT_DELAY_MS)
      }
    }

    connect()

    return () => {
      cancelled = true
      clearTimeout(reconnectTimerRef.current)
      socketRef.current?.close()
    }
  }, [path])

  function dismiss(index) {
    setMessages((prev) => prev.filter((_, i) => i !== index))
  }

  return { messages, connected, error, dismiss }
}
