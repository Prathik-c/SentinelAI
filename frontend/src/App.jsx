import { useEffect, useState } from "react"
import axios from "axios"
import HealthMonitor from "./components/HealthMonitor"
import AlertPanel from "./components/AlertPanel"
import ChatInterface from "./components/ChatInterface"

export default function App() {
  const [status, setStatus] = useState("checking...")

  useEffect(() => {
    axios.get("http://localhost:8000/ping")
      .then(res => setStatus(res.data.message))
      .catch(() => setStatus("backend not reachable"))
  }, [])

  return (
    <div className="min-h-screen bg-slate-900 p-8">
      <h1 className="text-3xl font-bold text-white mb-2">SentinelAI</h1>
      <p className="text-slate-400 mb-6">
        Backend status:
        <span className="text-green-400 ml-2 font-mono">{status}</span>
      </p>

      <HealthMonitor />
      <div className="mt-6">
        <AlertPanel />
        <div className="mt-6">
          <ChatInterface />
        </div>
      </div>
    </div>
  )
}