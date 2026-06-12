// frontend/src/hooks/useWebSocket.js
import { useEffect, useState } from "react"

export function useWebSocket(url) {
  const [data, setData] = useState(null)
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    const ws = new WebSocket(url)

    ws.onopen = () => setConnected(true)
    ws.onmessage = (event) => setData(JSON.parse(event.data))
    ws.onclose = () => setConnected(false)
    ws.onerror = () => setConnected(false)

    return () => ws.close()
  }, [url])

  return { data, connected }
}