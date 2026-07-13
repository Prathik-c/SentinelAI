import { useWebSocket } from "../hooks/useWebSocket"
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from "recharts"
import { useState, useEffect } from "react"
import axios from "axios"
import { Cpu, Database, HardDrive, ShieldAlert, Sliders } from "lucide-react"

export default function HealthMonitor({ onThresholdChange }) {
  const { data, connected } = useWebSocket("ws://localhost:8000/ws/health")
  const [history, setHistory] = useState([])
  const [baseline, setBaseline] = useState(null)
  
  // Custom threshold configurations
  const [cpuMult, setCpuMult] = useState(3.0)
  const [ramMargin, setRamMargin] = useState(20.0)

  // Load configuration and baseline
  useEffect(() => {
    const savedCpu = localStorage.getItem("sentinel_cpu_mult")
    const savedRam = localStorage.getItem("sentinel_ram_margin")
    if (savedCpu) setCpuMult(parseFloat(savedCpu))
    if (savedRam) setRamMargin(parseFloat(savedRam))

    fetchBaseline()
    
    // Fetch baseline every 60s
    const interval = setInterval(fetchBaseline, 60000)
    return () => clearInterval(interval)
  }, [])

  const fetchBaseline = () => {
    axios.get("http://localhost:8000/health/baseline")
      .then(res => {
        if (!res.data.error) {
          setBaseline(res.data)
        }
      })
      .catch(err => console.error("Error fetching baseline:", err))
  }

  // Handle live WebSocket update
  useEffect(() => {
    if (data) {
      setHistory(prev => {
        const updated = [...prev, { ...data, time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) }]
        return updated.slice(-20)
      })
    }
  }, [data])

  const handleCpuSlider = (val) => {
    setCpuMult(val)
    localStorage.setItem("sentinel_cpu_mult", val)
    if (onThresholdChange) onThresholdChange()
  }

  const handleRamSlider = (val) => {
    setRamMargin(val)
    localStorage.setItem("sentinel_ram_margin", val)
    if (onThresholdChange) onThresholdChange()
  }

  // Calculate dynamic threshold limits based on current baseline
  const cpuThresholdLimit = baseline?.cpu?.mean ? Math.min(baseline.cpu.mean * cpuMult, 80.0) : 40.0
  const ramThresholdLimit = baseline?.ram?.mean ? Math.min(baseline.ram.mean + ramMargin, 95.0) : 75.0

  return (
    <div className="bg-slate-800 rounded-xl p-6 text-white border border-slate-700/50 shadow-xl backdrop-blur-md">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-xl font-bold flex items-center gap-2">
          <Cpu className="text-blue-400" size={22} />
          System Health Telemetry
        </h2>
        <span className="flex items-center gap-2">
          <span className={`h-2.5 w-2.5 rounded-full ${connected ? "bg-green-500 animate-pulse" : "bg-red-500"}`}></span>
          <span className={`text-xs font-semibold ${connected ? "text-green-400" : "text-red-400"}`}>
            {connected ? "LIVE FEED" : "OFFLINE"}
          </span>
        </span>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        {/* CPU */}
        <div className="bg-slate-900/50 border border-slate-700 p-4 rounded-xl flex items-center justify-between">
          <div className="space-y-1">
            <span className="text-xs text-slate-400 font-bold uppercase tracking-wider">CPU Util</span>
            <div className="text-2xl font-black text-blue-400 font-mono">
              {data ? `${data.cpu.toFixed(1)}%` : "0.0%"}
            </div>
            {baseline && (
              <span className="text-[10px] text-slate-500 block">
                Your Baseline Mean: <b className="text-slate-400">{baseline.cpu.mean}%</b>
              </span>
            )}
          </div>
          <div className="bg-blue-500/10 p-3 rounded-lg border border-blue-500/20 text-blue-400">
            <Cpu size={24} />
          </div>
        </div>

        {/* RAM */}
        <div className="bg-slate-900/50 border border-slate-700 p-4 rounded-xl flex items-center justify-between">
          <div className="space-y-1">
            <span className="text-xs text-slate-400 font-bold uppercase tracking-wider">RAM Usage</span>
            <div className="text-2xl font-black text-green-400 font-mono">
              {data ? `${data.ram.toFixed(1)}%` : "0.0%"}
            </div>
            {baseline && (
              <span className="text-[10px] text-slate-500 block">
                Your Baseline Mean: <b className="text-slate-400">{baseline.ram.mean}%</b>
              </span>
            )}
          </div>
          <div className="bg-green-500/10 p-3 rounded-lg border border-green-500/20 text-green-400">
            <Database size={24} />
          </div>
        </div>

        {/* Disk */}
        <div className="bg-slate-900/50 border border-slate-700 p-4 rounded-xl flex items-center justify-between">
          <div className="space-y-1">
            <span className="text-xs text-slate-400 font-bold uppercase tracking-wider">Disk Util (C:)</span>
            <div className="text-2xl font-black text-amber-400 font-mono">
              {data ? `${data.disk.toFixed(1)}%` : "0.0%"}
            </div>
            {baseline && (
              <span className="text-[10px] text-slate-500 block">
                Your Baseline Mean: <b className="text-slate-400">{baseline.disk.mean}%</b>
              </span>
            )}
          </div>
          <div className="bg-amber-500/10 p-3 rounded-lg border border-amber-500/20 text-amber-400">
            <HardDrive size={24} />
          </div>
        </div>
      </div>

      {/* Chart */}
      <div className="bg-slate-900/40 border border-slate-700 p-4 rounded-xl mb-6">
        <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4">Real-Time Metrics Chart</h3>
        <div className="h-60">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={history} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
              <XAxis dataKey="time" stroke="#475569" fontSize={9} />
              <YAxis domain={[0, 100]} stroke="#475569" fontSize={9} />
              <Tooltip
                contentStyle={{ backgroundColor: "#0f172a", borderColor: "#334155", borderRadius: "8px", color: "#e2e8f0", fontSize: "11px" }}
              />
              
              {/* CPU reference lines */}
              {baseline?.cpu?.mean && (
                <ReferenceLine y={baseline.cpu.mean} stroke="#2563eb" strokeDasharray="3 3" strokeOpacity={0.4} />
              )}
              {baseline && (
                <ReferenceLine y={cpuThresholdLimit} stroke="#ef4444" strokeDasharray="4 4" strokeOpacity={0.6} />
              )}

              {/* RAM reference lines */}
              {baseline?.ram?.mean && (
                <ReferenceLine y={baseline.ram.mean} stroke="#16a34a" strokeDasharray="3 3" strokeOpacity={0.4} />
              )}
              {baseline && (
                <ReferenceLine y={ramThresholdLimit} stroke="#f59e0b" strokeDasharray="4 4" strokeOpacity={0.6} />
              )}

              <Line type="monotone" dataKey="cpu" stroke="#3b82f6" strokeWidth={2.5} dot={false} activeDot={{ r: 4 }} name="CPU %" />
              <Line type="monotone" dataKey="ram" stroke="#22c55e" strokeWidth={2.5} dot={false} activeDot={{ r: 4 }} name="RAM %" />
              <Line type="monotone" dataKey="disk" stroke="#f59e0b" strokeWidth={1.5} dot={false} name="Disk %" />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className="flex flex-wrap gap-4 justify-center mt-3 text-[10px] text-slate-400">
          <span className="flex items-center gap-1.5"><span className="h-1.5 w-6 bg-blue-500 rounded"></span> CPU Live</span>
          <span className="flex items-center gap-1.5"><span className="h-1.5 w-6 bg-green-500 rounded"></span> RAM Live</span>
          {baseline && (
            <>
              <span className="flex items-center gap-1.5"><span className="h-0.5 w-6 border-t-2 border-dashed border-blue-600"></span> CPU Mean ({baseline.cpu.mean}%)</span>
              <span className="flex items-center gap-1.5"><span className="h-0.5 w-6 border-t-2 border-dashed border-red-500"></span> CPU Alert Limit ({cpuThresholdLimit.toFixed(1)}%)</span>
              <span className="flex items-center gap-1.5"><span className="h-0.5 w-6 border-t-2 border-dashed border-green-600"></span> RAM Mean ({baseline.ram.mean}%)</span>
              <span className="flex items-center gap-1.5"><span className="h-0.5 w-6 border-t-2 border-dashed border-amber-500"></span> RAM Alert Limit ({ramThresholdLimit.toFixed(1)}%)</span>
            </>
          )}
        </div>
      </div>

      {/* Threshold Controls */}
      <div className="bg-slate-900/50 border border-slate-700 p-4 rounded-xl">
        <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2 mb-4">
          <Sliders className="text-indigo-400" size={16} />
          Calibration Settings (Thresholds)
        </h3>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-2">
            <div className="flex justify-between text-xs">
              <span className="text-slate-350 font-semibold flex items-center gap-1">
                CPU Anomaly Multiplier
              </span>
              <span className="text-blue-400 font-mono font-bold">{cpuMult.toFixed(1)}x Baseline</span>
            </div>
            <input
              type="range"
              min="1.5"
              max="5.0"
              step="0.5"
              value={cpuMult}
              onChange={(e) => handleCpuSlider(parseFloat(e.target.value))}
              className="w-full h-1.5 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-blue-500"
            />
            <p className="text-[10px] text-slate-500">
              Flags CPU anomalies when utilization exceeds this multiple of your normal baseline mean.
            </p>
          </div>

          <div className="space-y-2">
            <div className="flex justify-between text-xs">
              <span className="text-slate-350 font-semibold flex items-center gap-1">
                RAM Anomaly Safety Margin
              </span>
              <span className="text-green-400 font-mono font-bold">+{ramMargin.toFixed(0)}% Mean</span>
            </div>
            <input
              type="range"
              min="5"
              max="40"
              step="5"
              value={ramMargin}
              onChange={(e) => handleRamSlider(parseFloat(e.target.value))}
              className="w-full h-1.5 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-green-500"
            />
            <p className="text-[10px] text-slate-500">
              Flags RAM anomalies when usage exceeds your baseline mean by this safety percentage margin.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}