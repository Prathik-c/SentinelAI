import { useState } from "react"
import axios from "axios"
import {
  Terminal, AlertTriangle, Shield, Clock, ChevronDown,
  ChevronUp, CheckCircle, XCircle, Loader, Info
} from "lucide-react"

const API = "http://localhost:8000"

/**
 * IncidentDetail — Expandable card showing full structured incident data.
 * Can be used standalone or embedded in AlertPanel.
 *
 * Props:
 *   incident    — incident object from /alerts endpoint
 *   onAction    — callback(id, action) when user approves/dismisses
 *   defaultOpen — if true, start expanded
 */
export default function IncidentDetail({ incident, onAction, defaultOpen = false }) {
  const [expanded,   setExpanded]   = useState(defaultOpen)
  const [actioning,  setActioning]  = useState(false)

  const handleAction = async (action) => {
    setActioning(true)
    try {
      await axios.post(`${API}/alerts/${incident.id}/action`, { action })
      onAction?.(incident.id, action)
    } catch (err) {
      console.error("IncidentDetail action error:", err)
    } finally {
      setActioning(false)
    }
  }

  // ── Visual helpers ──────────────────────────────────────────────────────
  const severityConfig = {
    critical: { border: "border-red-500/40",    bg: "bg-red-500/8",    badge: "bg-red-500/20 text-red-400 border-red-500/30" },
    high:     { border: "border-orange-500/40", bg: "bg-orange-500/8", badge: "bg-orange-500/20 text-orange-400 border-orange-500/30" },
    medium:   { border: "border-yellow-500/40", bg: "bg-yellow-500/8", badge: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30" },
    low:      { border: "border-slate-500/40",  bg: "bg-slate-500/8",  badge: "bg-slate-500/20 text-slate-400 border-slate-500/30" },
  }

  const riskLevel = (score) => {
    if (!score) return { label: "—",      color: "text-slate-500" }
    if (score >= 70) return { label: "HIGH",   color: "text-red-400" }
    if (score >= 40) return { label: "MEDIUM", color: "text-amber-400" }
    return           { label: "LOW",    color: "text-emerald-400" }
  }

  const sc   = severityConfig[incident.severity?.toLowerCase()] || severityConfig.medium
  const risk = riskLevel(incident.risk_score)

  return (
    <div className={`border rounded-xl transition-all duration-200 ${sc.border} ${sc.bg}`}>

      {/* ── Collapsed header (always visible) ─────────────────────────────── */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left p-4"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3 flex-1 min-w-0">
            {/* Type icon */}
            <div className="mt-0.5 shrink-0">
              {incident.type?.includes("process")
                ? <Terminal size={16} className="text-purple-400" />
                : incident.type?.includes("cpu")
                  ? <AlertTriangle size={16} className="text-orange-400" />
                  : <Shield size={16} className="text-red-400" />
              }
            </div>

            <div className="flex-1 min-w-0">
              {/* Type + severity badges */}
              <div className="flex items-center gap-2 flex-wrap mb-1">
                <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5
                                  rounded-md border ${sc.badge}`}>
                  {(incident.type || "").replace(/_/g, " ")}
                </span>
                {incident.process_name && (
                  <span className="text-[10px] font-mono text-slate-400 bg-slate-900/40
                                   px-2 py-0.5 rounded border border-slate-700/40">
                    {incident.process_name}
                  </span>
                )}
              </div>

              {/* Description */}
              <p className="text-sm font-semibold text-slate-100 truncate">
                {incident.description}
              </p>

              {/* Timestamp */}
              <div className="flex items-center gap-1 mt-1 text-[10px] text-slate-500">
                <Clock size={9} />
                {new Date(incident.timestamp).toLocaleString()}
              </div>
            </div>
          </div>

          {/* Right side: risk score + expand chevron */}
          <div className="flex items-center gap-3 shrink-0">
            {incident.risk_score != null && (
              <div className="text-right">
                <div className={`text-lg font-black ${risk.color}`}>
                  {Math.round(incident.risk_score)}
                </div>
                <div className="text-[9px] text-slate-500 font-bold">{risk.label} RISK</div>
              </div>
            )}
            {expanded
              ? <ChevronUp size={16} className="text-slate-400" />
              : <ChevronDown size={16} className="text-slate-400" />
            }
          </div>
        </div>
      </button>

      {/* ── Expanded detail ──────────────────────────────────────────────── */}
      {expanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-white/5 pt-3">

          {/* Detection reasons */}
          {incident.reasons?.length > 0 && (
            <div>
              <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1">
                <Info size={10} /> Detection Reasons
              </p>
              <ul className="space-y-1">
                {incident.reasons.map((r, i) => (
                  <li key={i} className="text-xs text-slate-300 flex items-start gap-2">
                    <span className="text-blue-400 mt-0.5 shrink-0">▸</span>
                    {r}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* CPU / RAM metrics */}
          {(incident.cpu != null || incident.ram != null) && (
            <div className="grid grid-cols-2 gap-2">
              {incident.cpu != null && (
                <div className="bg-slate-900/40 border border-slate-700/30 rounded-lg p-2.5 text-center">
                  <div className="text-xl font-black text-orange-400">{incident.cpu.toFixed(1)}%</div>
                  <div className="text-[9px] text-slate-500">CPU at detection</div>
                </div>
              )}
              {incident.ram != null && (
                <div className="bg-slate-900/40 border border-slate-700/30 rounded-lg p-2.5 text-center">
                  <div className="text-xl font-black text-green-400">{incident.ram.toFixed(1)}%</div>
                  <div className="text-[9px] text-slate-500">RAM at detection</div>
                </div>
              )}
            </div>
          )}

          {/* AI explanation */}
          {incident.report ? (
            <div>
              <p className="text-[10px] font-bold text-blue-400 uppercase tracking-wider mb-1.5 flex items-center gap-1">
                ⚡ AI Explanation
              </p>
              <div className="bg-slate-900/50 border border-blue-500/10 rounded-lg p-3
                              text-xs text-slate-300 leading-relaxed">
                {incident.report}
              </div>
            </div>
          ) : (
            <div className="text-[11px] text-slate-500 italic flex items-center gap-1.5">
              <Loader size={10} className="animate-spin" />
              AI explanation is being generated in the background…
            </div>
          )}

          {/* Status + action buttons */}
          <div className="flex items-center justify-between pt-1">
            <div className="flex items-center gap-1.5 text-xs">
              {incident.status === "approved"
                ? <><CheckCircle size={14} className="text-emerald-400" /><span className="text-emerald-400">Acknowledged</span></>
                : incident.status === "dismissed"
                  ? <><XCircle size={14} className="text-slate-400" /><span className="text-slate-400">Dismissed</span></>
                  : <><Clock size={14} className="text-yellow-400" /><span className="text-yellow-400">Awaiting review</span></>
              }
            </div>

            {incident.status === "pending" && (
              <div className="flex gap-2">
                <button
                  onClick={() => handleAction("approved")}
                  disabled={actioning}
                  className="bg-emerald-600/80 hover:bg-emerald-500 disabled:opacity-50 text-white
                             text-xs font-bold px-3 py-1.5 rounded-lg transition-all"
                >
                  {actioning ? <Loader size={11} className="animate-spin" /> : "✓ Acknowledge"}
                </button>
                <button
                  onClick={() => handleAction("dismissed")}
                  disabled={actioning}
                  className="bg-slate-700/80 hover:bg-slate-600 disabled:opacity-50 text-slate-200
                             text-xs font-bold px-3 py-1.5 rounded-lg border border-slate-600 transition-all"
                >
                  Dismiss
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
