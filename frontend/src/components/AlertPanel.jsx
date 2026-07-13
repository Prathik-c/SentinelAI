import { useState, useEffect, useRef } from "react"
import axios from "axios"
import {
  AlertTriangle, CheckCircle, XCircle, Clock,
  Loader, RefreshCw, Shield, ChevronDown, ChevronUp,
  Zap, Activity
} from "lucide-react"

const API = "http://localhost:8000"

export default function AlertPanel({ refreshTrigger }) {
  const [alerts,   setAlerts]   = useState([])
  const [filter,   setFilter]   = useState("pending")
  const [loading,  setLoading]  = useState(false)
  const [scanning, setScanning] = useState(false)
  const [expanded, setExpanded] = useState({})
  const intervalRef = useRef(null)

  // ── Data fetching ─────────────────────────────────────────────────────────
  const fetchAlerts = async () => {
    setLoading(true)
    try {
      const res = await axios.get(`${API}/alerts?limit=100`)
      setAlerts(res.data)
    } catch (err) {
      console.error("fetchAlerts error:", err)
    } finally {
      setLoading(false)
    }
  }

  // Anomaly scan now returns fast (< 100ms) — LLM fills in async
  const scanForAnomalies = async () => {
    setScanning(true)
    try {
      await axios.get(`${API}/health/anomaly/check`)
      await fetchAlerts()
    } catch (err) {
      console.error("scan error:", err)
    } finally {
      setScanning(false)
    }
  }

  const handleAction = async (id, action) => {
    try {
      const res = await axios.post(`${API}/alerts/${id}/action`, { action })
      setAlerts(prev => prev.map(a => a.id === id ? res.data : a))
    } catch (err) {
      console.error(`handleAction ${action} on ${id}:`, err)
    }
  }

  const toggleExpand = (id) =>
    setExpanded(prev => ({ ...prev, [id]: !prev[id] }))

  // Poll every 60s (reduced from 30s — detection is now background task)
  useEffect(() => {
    fetchAlerts()
    intervalRef.current = setInterval(fetchAlerts, 60000)
    return () => clearInterval(intervalRef.current)
  }, [refreshTrigger])

  // ── Filters ───────────────────────────────────────────────────────────────
  const filteredAlerts = alerts.filter(a =>
    filter === "all" ? true : a.status === filter
  )

  const countFor = (f) =>
    f === "all" ? alerts.length : alerts.filter(a => a.status === f).length

  // ── Styling helpers ───────────────────────────────────────────────────────
  const severityStyle = (sev) => {
    switch (sev?.toLowerCase()) {
      case "critical": return "bg-red-500/10 border-red-500/25 text-red-400"
      case "high":     return "bg-orange-500/10 border-orange-500/25 text-orange-400"
      case "medium":   return "bg-yellow-500/10 border-yellow-500/25 text-yellow-400"
      default:         return "bg-slate-500/10 border-slate-500/25 text-slate-400"
    }
  }

  const riskBadgeStyle = (score) => {
    if (!score) return "bg-slate-700 text-slate-400"
    if (score >= 70) return "bg-red-500/20 text-red-400 border border-red-500/30"
    if (score >= 40) return "bg-orange-500/20 text-orange-400 border border-orange-500/30"
    return "bg-green-500/20 text-green-400 border border-green-500/30"
  }

  const statusIcon = (status) => {
    if (status === "approved")  return <CheckCircle className="text-emerald-400" size={14} />
    if (status === "dismissed") return <XCircle className="text-slate-500" size={14} />
    return <Clock className="text-yellow-400 animate-pulse" size={14} />
  }

  return (
    <div className="bg-slate-800/80 rounded-2xl p-5 text-white border border-slate-700/50 shadow-2xl backdrop-blur-md">

      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-3 mb-5">
        <div>
          <h2 className="text-lg font-bold flex items-center gap-2">
            <AlertTriangle className="text-amber-400" size={20} />
            Behavioral Anomalies
          </h2>
          <p className="text-[11px] text-slate-500 mt-0.5">
            Instant Python detection · AI explanations load asynchronously
          </p>
        </div>

        <button
          onClick={scanForAnomalies}
          disabled={scanning}
          className="flex items-center gap-1.5 bg-slate-700/80 hover:bg-slate-600/80 disabled:opacity-50
                     text-xs font-semibold px-3 py-2 rounded-lg border border-slate-600/50 transition-all"
        >
          {scanning
            ? <><Loader size={13} className="animate-spin" /> Scanning…</>
            : <><RefreshCw size={13} /> Scan Now</>
          }
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-5 bg-slate-900/50 p-1 rounded-xl">
        {["pending", "approved", "dismissed", "all"].map(tab => (
          <button
            key={tab}
            onClick={() => setFilter(tab)}
            className={`flex-1 py-1.5 text-xs font-semibold rounded-lg capitalize transition-all ${
              filter === tab
                ? "bg-blue-600 text-white shadow-lg shadow-blue-900/30"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            {tab} <span className="opacity-60">({countFor(tab)})</span>
          </button>
        ))}
      </div>

      {/* Alert list */}
      {loading && !alerts.length ? (
        <div className="flex items-center justify-center py-10 text-slate-500 gap-2 text-sm">
          <Loader size={16} className="animate-spin" /> Loading alerts…
        </div>
      ) : filteredAlerts.length === 0 ? (
        <div className="text-center py-10 text-slate-500 border border-dashed border-slate-700 rounded-xl">
          <Shield className="mx-auto mb-2 text-slate-600" size={28} />
          <p className="text-sm font-semibold">No {filter !== "all" ? filter : ""} alerts</p>
          <p className="text-xs mt-1">System behaviour is within normal parameters.</p>
        </div>
      ) : (
        <div className="space-y-3 max-h-[520px] overflow-y-auto pr-1 scrollbar-thin">
          {filteredAlerts.map(alert => (
            <div
              key={alert.id}
              className={`border rounded-xl p-3.5 transition-all ${severityStyle(alert.severity)}`}
            >
              {/* Top row: type + metadata badges */}
              <div className="flex items-start justify-between gap-2 mb-2">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-[10px] font-bold uppercase tracking-wider
                                   bg-black/20 px-2 py-0.5 rounded-md border border-white/5">
                    {(alert.type || "").replace(/_/g, " ")}
                  </span>
                  {alert.process_name && (
                    <span className="text-[10px] font-mono bg-slate-900/40 px-2 py-0.5 rounded border border-white/5 text-slate-300">
                      {alert.process_name}
                    </span>
                  )}
                  <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${riskBadgeStyle(alert.risk_score)}`}>
                    {alert.risk_score != null ? `Risk: ${Math.round(alert.risk_score)}` : ""}
                  </span>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  {statusIcon(alert.status)}
                  <span className="text-[10px] capitalize text-slate-400 font-semibold">
                    {alert.status}
                  </span>
                </div>
              </div>

              {/* Description */}
              <p className="text-sm font-semibold text-slate-100 mb-1">
                {alert.description}
              </p>

              {/* Timestamp */}
              <p className="text-[10px] text-slate-500 font-mono mb-2">
                {new Date(alert.timestamp).toLocaleString()}
              </p>

              {/* Reasons list */}
              {alert.reasons?.length > 0 && (
                <div className="mb-2">
                  <div className="flex flex-wrap gap-1">
                    {alert.reasons.map((r, i) => (
                      <span key={i} className="text-[10px] bg-black/20 border border-white/5
                                               px-2 py-0.5 rounded-full text-slate-300">
                        {r}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* AI Explanation (expandable) */}
              {alert.report ? (
                <div className="mt-2">
                  <button
                    onClick={() => toggleExpand(alert.id)}
                    className="flex items-center gap-1 text-[10px] text-blue-400 hover:text-blue-300
                               font-semibold uppercase tracking-wide transition-colors"
                  >
                    <Zap size={10} />
                    AI Explanation
                    {expanded[alert.id]
                      ? <ChevronUp size={10} />
                      : <ChevronDown size={10} />
                    }
                  </button>
                  {expanded[alert.id] && (
                    <div className="mt-1.5 bg-slate-900/40 border border-slate-700/30
                                    rounded-lg p-3 text-xs text-slate-300 leading-relaxed">
                      {alert.report}
                    </div>
                  )}
                </div>
              ) : alert.status === "pending" ? (
                <p className="text-[10px] text-slate-500 italic mt-1.5 flex items-center gap-1">
                  <Activity size={9} className="animate-pulse" />
                  AI explanation loading…
                </p>
              ) : null}

              {/* Action buttons */}
              {alert.status === "pending" && (
                <div className="flex gap-2 mt-3">
                  <button
                    onClick={() => handleAction(alert.id, "approved")}
                    className="flex-1 bg-emerald-600/80 hover:bg-emerald-500 text-white
                               text-xs font-bold py-1.5 rounded-lg transition-all"
                  >
                    ✓ Acknowledge
                  </button>
                  <button
                    onClick={() => handleAction(alert.id, "dismissed")}
                    className="flex-1 bg-slate-700/80 hover:bg-slate-600 text-slate-200
                               text-xs font-bold py-1.5 rounded-lg border border-slate-600 transition-all"
                  >
                    Dismiss
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}