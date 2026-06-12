import { useEffect, useState } from "react"
import axios from "axios"

export default function App() {
  const [status, setStatus] = useState("checking...")

  useEffect(() => {
    axios.get("http://localhost:8000/ping")
      .then(res => setStatus(res.data.message))
      .catch(() => setStatus("backend not reachable"))
  }, [])

  return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center">
      <div className="text-center">
        <h1 className="text-4xl font-bold text-white mb-4">SentinelAI</h1>
        <p className="text-slate-400">Backend status: 
          <span className="text-green-400 ml-2 font-mono">{status}</span>
        </p>
      </div>
    </div>
  )
}