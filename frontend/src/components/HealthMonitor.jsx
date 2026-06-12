import { useWebSocket } from "../hooks/useWebSocket"
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts"
import { useState, useEffect } from "react"

export default function HealthMonitor() {
  const { data, connected } = useWebSocket("ws://localhost:8000/ws/health")
  const [history, setHistory] = useState([])

  useEffect(() => {
    if (data) {
      setHistory(prev => {
        const updated = [...prev, { ...data, time: new Date().toLocaleTimeString() }]
        return updated.slice(-20)
      })
    }
  }, [data])

  return (
    <div className="bg-slate-800 rounded-xl p-6 text-white">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-bold">System Health</h2>
        <span className={`text-sm ${connected ? "text-green-400" : "text-red-400"}`}>
          {connected ? "● Live" : "● Disconnected"}
        </span>
      </div>

      <ResponsiveContainer width="100%" height={250}>
        <LineChart data={history}>
          <XAxis dataKey="time" stroke="#94a3b8" />
          <YAxis domain={[0, 100]} stroke="#94a3b8" />
          <Tooltip />
          <Line type="monotone" dataKey="cpu" stroke="#3b82f6" name="CPU %" />
          <Line type="monotone" dataKey="ram" stroke="#22c55e" name="RAM %" />
          <Line type="monotone" dataKey="disk" stroke="#f59e0b" name="Disk %" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}