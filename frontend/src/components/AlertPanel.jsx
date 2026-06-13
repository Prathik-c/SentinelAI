import { useWebSocket } from "../hooks/useWebSocket"
import { useState, useEffect } from "react"
import { AlertTriangle } from "lucide-react"

export default function AlertPanel() {
  const { data, connected } = useWebSocket("ws://localhost:8000/face/ws/alerts")
  const [alerts, setAlerts] = useState([])

  useEffect(() => {
    if (data) {
      setAlerts(prev => [data, ...prev])
    }
  }, [data])

  return (
    <div className="bg-slate-800 rounded-xl p-6 text-white">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-bold flex items-center gap-2">
          <AlertTriangle className="text-yellow-400" size={20} />
          Alerts
        </h2>
        <span className={`text-sm ${connected ? "text-green-400" : "text-red-400"}`}>
          {connected ? "● Monitoring" : "● Offline"}
        </span>
      </div>

      {alerts.length === 0 && (
        <p className="text-slate-400 text-sm">No alerts yet.</p>
      )}

      <div className="space-y-3">
        {alerts.map(alert => (
          <div key={alert.id} className="bg-slate-700 rounded-lg p-4 flex gap-4">
            <div className="flex-1">
              <p className="font-semibold">{alert.description}</p>
              <p className="text-xs text-slate-400">{alert.timestamp}</p>
              <span className="inline-block mt-1 text-xs bg-yellow-500/20 text-yellow-400 px-2 py-1 rounded">
                {alert.status}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}