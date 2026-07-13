import { useState, useEffect } from "react"
import axios from "axios"
import {
  FileText, Mail, Settings, Check, AlertCircle,
  Loader, TrendingUp, Shield, Calendar, Download,
  Heart, Zap
} from "lucide-react"

const API = "http://localhost:8000"

export default function ReportPanel() {
  const [days,          setDays]          = useState(7)
  const [generating,    setGenerating]    = useState(false)
  const [genWeekly,     setGenWeekly]     = useState(false)
  const [sending,       setSending]       = useState(false)
  const [status,        setStatus]        = useState({ type: "", message: "" })
  const [showConfig,    setShowConfig]    = useState(false)
  const [latestReport,  setLatestReport]  = useState(null)

  const [smtpConfig, setSmtpConfig] = useState({
    smtp_host: "", smtp_port: 587, smtp_user: "",
    smtp_password: "", recipient: ""
  })

  // Load saved config + fetch latest weekly report
  useEffect(() => {
    const saved = localStorage.getItem("sentinel_smtp_config")
    if (saved) {
      try { setSmtpConfig(JSON.parse(saved)) } catch { /**/ }
    }
    fetchLatestReport()
  }, [])

  const fetchLatestReport = async () => {
    try {
      const res = await axios.get(`${API}/reports/weekly/latest`)
      if (res.data.status !== "no_report") setLatestReport(res.data)
    } catch { /**/ }
  }

  const handleConfigChange = (e) => {
    const updated = { ...smtpConfig, [e.target.name]: e.target.value }
    setSmtpConfig(updated)
    localStorage.setItem("sentinel_smtp_config", JSON.stringify(updated))
  }

  const downloadReport = async () => {
    setGenerating(true)
    setStatus({ type: "", message: "" })
    try {
      const res = await axios.post(
        `${API}/reports/generate`,
        { days },
        { responseType: "blob" }
      )
      const url  = window.URL.createObjectURL(new Blob([res.data]))
      const link = document.createElement("a")
      link.href = url
      link.setAttribute("download", `sentinel_report_${days}d.pdf`)
      document.body.appendChild(link)
      link.click()
      link.remove()
      setStatus({ type: "success", message: "PDF downloaded successfully!" })
    } catch {
      setStatus({ type: "error", message: "Failed to generate PDF. Make sure the backend is running." })
    } finally {
      setGenerating(false)
    }
  }

  const generateWeeklyReport = async () => {
    setGenWeekly(true)
    setStatus({ type: "", message: "" })
    try {
      await axios.post(`${API}/reports/generate-weekly`)
      await fetchLatestReport()
      setStatus({ type: "success", message: "Weekly report generated! Health & Risk scores updated." })
    } catch {
      setStatus({ type: "error", message: "Weekly report generation failed." })
    } finally {
      setGenWeekly(false)
    }
  }

  const emailReport = async (e) => {
    e.preventDefault()
    if (!smtpConfig.smtp_host || !smtpConfig.smtp_user || !smtpConfig.smtp_password || !smtpConfig.recipient) {
      setStatus({ type: "error", message: "Please fill out all SMTP settings." })
      return
    }
    setSending(true)
    setStatus({ type: "", message: "" })
    try {
      await axios.post(`${API}/reports/send-email`, {
        days, ...smtpConfig, smtp_port: parseInt(smtpConfig.smtp_port)
      })
      setStatus({ type: "success", message: `Report emailed to ${smtpConfig.recipient}!` })
    } catch (err) {
      const detail = err.response?.data?.detail || "SMTP failed. Check credentials."
      setStatus({ type: "error", message: detail })
    } finally {
      setSending(false)
    }
  }

  // Score colour helpers
  const healthColor = (s) =>
    s >= 70 ? "text-emerald-400" : s >= 40 ? "text-amber-400" : "text-red-400"
  const riskColor = (s) =>
    s <= 30 ? "text-emerald-400" : s <= 60 ? "text-amber-400" : "text-red-400"

  return (
    <div className="bg-slate-800/80 rounded-2xl p-5 text-white border border-slate-700/50 shadow-2xl backdrop-blur-md">

      {/* Header */}
      <div className="flex justify-between items-center mb-5">
        <h2 className="text-lg font-bold flex items-center gap-2">
          <FileText className="text-emerald-400" size={20} />
          System Health Reports
        </h2>
        <button
          onClick={() => setShowConfig(!showConfig)}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all ${
            showConfig
              ? "bg-slate-700 border-slate-600 text-white"
              : "bg-slate-800/50 hover:bg-slate-700 border-slate-700 text-slate-400 hover:text-white"
          }`}
        >
          <Settings size={13} className={showConfig ? "animate-spin" : ""} />
          SMTP
        </button>
      </div>

      {/* Latest Weekly Report Scores */}
      {latestReport && (
        <div className="grid grid-cols-2 gap-3 mb-5">
          <div className="bg-slate-900/50 border border-slate-700/50 rounded-xl p-3 text-center">
            <div className="flex items-center justify-center gap-1.5 mb-1">
              <Heart size={13} className="text-emerald-400" />
              <span className="text-[10px] text-slate-400 uppercase tracking-wide font-bold">Health Score</span>
            </div>
            <div className={`text-3xl font-black ${healthColor(latestReport.health_score)}`}>
              {latestReport.health_score}
              <span className="text-base font-normal text-slate-500">/100</span>
            </div>
          </div>
          <div className="bg-slate-900/50 border border-slate-700/50 rounded-xl p-3 text-center">
            <div className="flex items-center justify-center gap-1.5 mb-1">
              <Shield size={13} className="text-red-400" />
              <span className="text-[10px] text-slate-400 uppercase tracking-wide font-bold">Risk Score</span>
            </div>
            <div className={`text-3xl font-black ${riskColor(latestReport.risk_score)}`}>
              {latestReport.risk_score}
              <span className="text-base font-normal text-slate-500">/100</span>
            </div>
          </div>

          {/* Last generated timestamp */}
          <div className="col-span-2 flex items-center gap-1.5 text-[10px] text-slate-500">
            <Calendar size={10} />
            Last report: {new Date(latestReport.generated_at).toLocaleString()}
          </div>
        </div>
      )}

      {/* Actions row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mb-4">
        {/* Report window selector */}
        <div className="flex flex-col gap-1">
          <label className="text-[10px] text-slate-400 font-semibold uppercase tracking-wide">
            Period
          </label>
          <select
            value={days}
            onChange={e => setDays(Number(e.target.value))}
            className="bg-slate-700/60 border border-slate-600/40 text-sm rounded-xl px-3 py-2
                       outline-none focus:ring-2 focus:ring-emerald-500/40 text-white"
          >
            <option value={1}>24 Hours</option>
            <option value={3}>3 Days</option>
            <option value={7}>7 Days</option>
            <option value={30}>30 Days</option>
          </select>
        </div>

        {/* Download PDF */}
        <button
          onClick={downloadReport}
          disabled={generating}
          className="flex items-center justify-center gap-2 bg-emerald-600/80 hover:bg-emerald-500
                     disabled:opacity-50 text-white text-sm font-semibold rounded-xl px-4 py-2
                     transition-all shadow-lg shadow-emerald-900/20 self-end"
        >
          {generating
            ? <><Loader size={14} className="animate-spin" /> Generating…</>
            : <><Download size={14} /> Download PDF</>
          }
        </button>

        {/* Generate Weekly */}
        <button
          onClick={generateWeeklyReport}
          disabled={genWeekly}
          className="flex items-center justify-center gap-2 bg-blue-600/80 hover:bg-blue-500
                     disabled:opacity-50 text-white text-sm font-semibold rounded-xl px-4 py-2
                     transition-all shadow-lg shadow-blue-900/20 self-end"
        >
          {genWeekly
            ? <><Loader size={14} className="animate-spin" /> Generating…</>
            : <><Zap size={14} /> Generate Weekly</>
          }
        </button>
      </div>

      {/* Latest report stats preview */}
      {latestReport?.stats && (
        <div className="bg-slate-900/40 border border-slate-700/30 rounded-xl p-3 mb-4 space-y-2">
          <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wide flex items-center gap-1">
            <TrendingUp size={10} /> Latest Weekly Stats
          </p>
          <div className="grid grid-cols-3 gap-2 text-center">
            <div>
              <div className="text-base font-black text-blue-400">{latestReport.stats.avg_cpu?.toFixed(1)}%</div>
              <div className="text-[9px] text-slate-500">Avg CPU</div>
            </div>
            <div>
              <div className="text-base font-black text-green-400">{latestReport.stats.avg_ram?.toFixed(1)}%</div>
              <div className="text-[9px] text-slate-500">Avg RAM</div>
            </div>
            <div>
              <div className="text-base font-black text-amber-400">{latestReport.stats.total_anomalies ?? 0}</div>
              <div className="text-[9px] text-slate-500">Anomalies</div>
            </div>
          </div>
          {latestReport.stats.recommendations?.length > 0 && (
            <div className="pt-1 border-t border-slate-700/30">
              <p className="text-[9px] text-slate-500 uppercase tracking-wide font-bold mb-1">Top Recommendation</p>
              <p className="text-[11px] text-slate-300">{latestReport.stats.recommendations[0]}</p>
            </div>
          )}
        </div>
      )}

      {/* SMTP Config */}
      {showConfig && (
        <form onSubmit={emailReport} className="bg-slate-900/40 border border-slate-700/30 rounded-xl p-4 space-y-3 mb-4">
          <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
            <Mail size={14} className="text-blue-400" />
            Email Configuration
          </h3>
          <div className="grid grid-cols-3 gap-2">
            <div className="col-span-2">
              <input type="text" name="smtp_host" placeholder="SMTP Server (smtp.gmail.com)"
                value={smtpConfig.smtp_host} onChange={handleConfigChange} required
                className="w-full bg-slate-700/60 border border-slate-600/40 text-xs rounded-lg px-3 py-2
                           text-white outline-none focus:ring-1 focus:ring-blue-500/50" />
            </div>
            <input type="number" name="smtp_port" placeholder="Port"
              value={smtpConfig.smtp_port} onChange={handleConfigChange} required
              className="bg-slate-700/60 border border-slate-600/40 text-xs rounded-lg px-3 py-2
                         text-white outline-none focus:ring-1 focus:ring-blue-500/50" />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <input type="text" name="smtp_user" placeholder="SMTP Username"
              value={smtpConfig.smtp_user} onChange={handleConfigChange} required
              className="bg-slate-700/60 border border-slate-600/40 text-xs rounded-lg px-3 py-2
                         text-white outline-none focus:ring-1 focus:ring-blue-500/50" />
            <input type="password" name="smtp_password" placeholder="App Password"
              value={smtpConfig.smtp_password} onChange={handleConfigChange} required
              className="bg-slate-700/60 border border-slate-600/40 text-xs rounded-lg px-3 py-2
                         text-white outline-none focus:ring-1 focus:ring-blue-500/50" />
          </div>
          <div className="flex gap-2">
            <input type="email" name="recipient" placeholder="Recipient Email" value={smtpConfig.recipient}
              onChange={handleConfigChange} required
              className="flex-1 bg-slate-700/60 border border-slate-600/40 text-xs rounded-lg px-3 py-2
                         text-white outline-none focus:ring-1 focus:ring-blue-500/50" />
            <button type="submit" disabled={sending}
              className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-xs font-semibold
                         px-4 py-2 rounded-lg text-white flex items-center gap-1.5 transition-all">
              {sending ? <><Loader size={12} className="animate-spin" /> Sending…</> : <><Mail size={12} /> Send</>}
            </button>
          </div>
        </form>
      )}

      {/* Status message */}
      {status.message && (
        <div className={`flex items-start gap-2.5 p-3 rounded-xl text-sm border ${
          status.type === "success"
            ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
            : "bg-red-500/10 border-red-500/20 text-red-400"
        }`}>
          {status.type === "success"
            ? <Check size={16} className="mt-0.5 shrink-0" />
            : <AlertCircle size={16} className="mt-0.5 shrink-0" />
          }
          <span>{status.message}</span>
        </div>
      )}
    </div>
  )
}
