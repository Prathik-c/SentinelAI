import { useEffect, useState } from "react"
import axios from "axios"
import HealthMonitor from "./components/HealthMonitor"
import AlertPanel from "./components/AlertPanel"
import ChatInterface from "./components/ChatInterface"
import ReportPanel from "./components/ReportPanel"
import { Shield, Activity, RefreshCw } from "lucide-react"

export default function App() {
  const [status, setStatus] = useState("checking...")
  const [refreshTrigger, setRefreshTrigger] = useState(0)

  const checkConnection = () => {
    setStatus("checking...")
    axios.get("http://localhost:8000/ping")
      .then(res => setStatus(res.data.message))
      .catch(() => setStatus("offline"))
  }


  useEffect(() => {
    checkConnection()
    const interval = setInterval(checkConnection, 10000)
    return () => clearInterval(interval)
  }, [])

  // Triggered when threshold sliders change to force alert panels to re-scan
  const handleThresholdChange = () => {
    setRefreshTrigger(prev => prev + 1)
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-blue-500/35">
      {/* Top Premium Bar */}
      <header className="border-b border-slate-800/80 bg-slate-900/50 backdrop-blur-md sticky top-0 z-50 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="bg-gradient-to-tr from-blue-600 to-indigo-600 p-2.5 rounded-xl shadow-lg shadow-blue-500/20 text-white">
            <Shield size={24} className="animate-pulse" />
          </div>
          <div>
            <h1 className="text-xl font-black tracking-tight bg-gradient-to-r from-white via-slate-100 to-slate-400 bg-clip-text text-transparent flex items-center gap-1.5">
              SentinelAI
              <span className="text-[10px] font-bold text-blue-500 px-2 py-0.5 bg-blue-500/10 rounded-full border border-blue-500/20">
                v2.0.0
              </span>
            </h1>
            <p className="text-[10px] text-slate-450 uppercase tracking-widest font-semibold flex items-center gap-1">
              <Activity size={10} className="text-emerald-400" />
              Privacy-First Security Node
            </p>
          </div>
        </div>
        
        <div className="flex items-center gap-3">
          <div className="bg-slate-900 border border-slate-800/80 px-3 py-1.5 rounded-lg flex items-center gap-2">
            <span className="text-[10px] font-bold text-slate-450 uppercase tracking-wider">daemon:</span>
            <span className={`text-xs font-mono font-bold ${status === "pong" ? "text-emerald-400" : "text-red-400"}`}>
              {status === "pong" ? "ACTIVE" : "OFFLINE"}
            </span>
          </div>
          <button
            onClick={checkConnection}
            className="p-2 bg-slate-850 hover:bg-slate-750 text-slate-350 hover:text-white rounded-lg transition border border-slate-800/50"
            title="Refresh daemon status"
          >
            <RefreshCw size={14} />
          </button>
        </div>
      </header>

      {/* Main Layout Grid */}
      <main className="flex-1 max-w-7-1xl w-full mx-auto p-6 grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Left Side (2 Columns Wide): Telemetry, Baselines, and Reporting */}
        <div className="lg:col-span-2 space-y-6">
          <HealthMonitor onThresholdChange={handleThresholdChange} />
          <ReportPanel />
        </div>

        {/* Right Side (1 Column Wide): Alerts Feed & Natural Language Chat */}
        <div className="lg:col-span-1 space-y-6">
          <AlertPanel refreshTrigger={refreshTrigger} />
          <ChatInterface />
        </div>
        
      </main>

      {/* Bottom Footer */}
      <footer className="border-t border-slate-900 bg-slate-950/80 py-4 text-center text-slate-500 text-[10px]">
        <p>© {new Date().getFullYear()} SentinelAI Project. Local security daemon running with zero cloud transmissions.</p>
      </footer>
    </div>
  )
}