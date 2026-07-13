// frontend/src/hooks/useWebSocket.js
// Improved WebSocket hook with exponential-backoff reconnection,
// error state, and proper cleanup to prevent memory leaks.

import { useEffect, useRef, useState, useCallback } from "react"

const RECONNECT_BASE_MS  = 1000   // Start at 1s
const RECONNECT_MAX_MS   = 30000  // Cap at 30s
const RECONNECT_FACTOR   = 2      // Double each attempt

export function useWebSocket(url) {
  const [data,      setData]      = useState(null)
  const [connected, setConnected] = useState(false)
  const [error,     setError]     = useState(null)

  // Stable refs so interval callbacks always see the latest values
  const wsRef         = useRef(null)
  const retryDelay    = useRef(RECONNECT_BASE_MS)
  const retryTimer    = useRef(null)
  const mountedRef    = useRef(true)   // Prevent state updates after unmount

  const connect = useCallback(() => {
    if (!mountedRef.current) return
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) return

    try {
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        if (!mountedRef.current) return
        setConnected(true)
        setError(null)
        retryDelay.current = RECONNECT_BASE_MS  // Reset backoff on success
      }

      ws.onmessage = (event) => {
        if (!mountedRef.current) return
        try {
          setData(JSON.parse(event.data))
        } catch {
          // Silently ignore malformed frames
        }
      }

      ws.onerror = () => {
        if (!mountedRef.current) return
        setConnected(false)
        setError("WebSocket connection error")
      }

      ws.onclose = () => {
        if (!mountedRef.current) return
        setConnected(false)
        wsRef.current = null

        // Schedule reconnect with exponential backoff
        retryTimer.current = setTimeout(() => {
          if (!mountedRef.current) return
          retryDelay.current = Math.min(
            retryDelay.current * RECONNECT_FACTOR,
            RECONNECT_MAX_MS,
          )
          connect()
        }, retryDelay.current)
      }
    } catch (err) {
      setError(`Failed to create WebSocket: ${err.message}`)
    }
  }, [url])

  useEffect(() => {
    mountedRef.current = true
    connect()

    return () => {
      mountedRef.current = false
      clearTimeout(retryTimer.current)
      if (wsRef.current) {
        wsRef.current.onclose = null  // Prevent reconnect on intentional unmount
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [connect])

  return { data, connected, error }
}