import { useState, useRef, useEffect } from "react"
import axios from "axios"
import { MessageCircle, Send, Loader, X, Lightbulb, Clock } from "lucide-react"

const API = "http://localhost:8000"

// Suggested questions based on fine-tuning data patterns
const SUGGESTED_QUESTIONS = [
  "Is my system healthy right now?",
  "When did my RAM last spike?",
  "What processes are using the most CPU?",
  "Were any anomalies detected today?",
  "What was running last night?",
  "Show me disk usage history",
]

export default function ChatInterface() {
  const [question,  setQuestion]  = useState("")
  const [messages,  setMessages]  = useState([])
  const [loading,   setLoading]   = useState(false)
  const [showTips,  setShowTips]  = useState(true)
  const messagesEndRef = useRef(null)
  const cancelTokenRef = useRef(null)
  const inputRef       = useRef(null)

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, loading])

  const askQuestion = async (q = question) => {
    const text = (q || "").trim()
    if (!text || loading) return

    setQuestion("")
    setShowTips(false)
    setMessages(prev => [...prev, { role: "user", content: text, time: new Date() }])
    setLoading(true)

    // Create cancel token
    cancelTokenRef.current = axios.CancelToken.source()

    try {
      const res = await axios.post(
        `${API}/chat/ask`,
        { question: text },
        { cancelToken: cancelTokenRef.current.token, timeout: 120000 }
      )
      setMessages(prev => [...prev, {
        role:    "assistant",
        content: res.data.answer,
        intent:  res.data.intent,
        time:    new Date(),
      }])
    } catch (err) {
      if (axios.isCancel(err)) return  // User cancelled — no error message

      const msg = err.code === "ECONNABORTED"
        ? "⚠️ Request timed out. The local AI model may be loading. Please try again."
        : "⚠️ Couldn't process that right now. Make sure Ollama is running."

      setMessages(prev => [...prev, { role: "assistant", content: msg, time: new Date() }])
    } finally {
      setLoading(false)
      cancelTokenRef.current = null
      setTimeout(() => inputRef.current?.focus(), 100)
    }
  }

  const cancelRequest = () => {
    cancelTokenRef.current?.cancel("User cancelled")
    setLoading(false)
  }

  const handleKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      askQuestion()
    }
  }

  const clearChat = () => {
    setMessages([])
    setShowTips(true)
  }

  const intentLabel = (intent) => {
    const map = {
      RAM_SPIKE:      "RAM",
      CPU_QUERY:      "CPU",
      DISK_QUERY:     "Disk",
      TIME_QUERY:     "Timeline",
      PROCESS_QUERY:  "Process",
      INCIDENT_QUERY: "Alerts",
      HEALTH_CHECK:   "Health",
      GENERAL:        null,
    }
    return map[intent] || null
  }

  return (
    <div className="bg-slate-800/80 rounded-2xl p-5 text-white border border-slate-700/50 shadow-2xl backdrop-blur-md flex flex-col">

      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <MessageCircle className="text-blue-400" size={18} />
          <h2 className="text-lg font-bold">Ask SentinelAI</h2>
        </div>
        {messages.length > 0 && (
          <button
            onClick={clearChat}
            className="text-[10px] text-slate-500 hover:text-slate-300 flex items-center gap-1 transition-colors"
          >
            <X size={11} /> Clear
          </button>
        )}
      </div>

      {/* Message area */}
      <div className="flex-1 overflow-y-auto space-y-3 mb-4 max-h-80 min-h-[120px] scrollbar-thin">

        {showTips && messages.length === 0 && (
          <div className="space-y-2">
            <div className="flex items-center gap-1.5 text-xs text-slate-400 font-semibold">
              <Lightbulb size={13} className="text-amber-400" />
              Suggested questions
            </div>
            <div className="flex flex-wrap gap-1.5">
              {SUGGESTED_QUESTIONS.map((q, i) => (
                <button
                  key={i}
                  onClick={() => askQuestion(q)}
                  className="text-[11px] bg-slate-700/60 hover:bg-blue-600/30 border border-slate-600/50
                             hover:border-blue-500/30 text-slate-300 hover:text-blue-200
                             px-2.5 py-1 rounded-full transition-all"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, idx) => (
          <div key={idx} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            <div className="max-w-[88%] space-y-1">
              {/* Intent badge for assistant messages */}
              {msg.role === "assistant" && msg.intent && intentLabel(msg.intent) && (
                <span className="text-[9px] font-bold uppercase tracking-wide text-blue-400
                                 bg-blue-500/10 border border-blue-500/20 px-2 py-0.5 rounded-full
                                 inline-block mb-1">
                  {intentLabel(msg.intent)} context
                </span>
              )}
              <div className={`px-3.5 py-2.5 rounded-2xl text-sm leading-relaxed ${
                msg.role === "user"
                  ? "bg-blue-600 text-white rounded-br-sm"
                  : "bg-slate-700/80 text-slate-200 rounded-bl-sm border border-slate-600/30"
              }`}>
                {msg.content}
              </div>
              <div className="flex items-center gap-1 text-[9px] text-slate-600">
                <Clock size={8} />
                {msg.time?.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
              </div>
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-slate-700/60 border border-slate-600/30 px-4 py-2.5 rounded-2xl
                            rounded-bl-sm flex items-center gap-2.5 text-sm text-slate-400">
              <Loader size={13} className="animate-spin text-blue-400" />
              <span>Analyzing your system data…</span>
              <button
                onClick={cancelRequest}
                className="ml-1 text-xs text-slate-500 hover:text-red-400 transition-colors"
              >
                ✕
              </button>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="flex gap-2">
        <input
          ref={inputRef}
          type="text"
          value={question}
          onChange={e => setQuestion(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Ask about your system…"
          disabled={loading}
          className="flex-1 bg-slate-700/60 border border-slate-600/40 text-white
                     placeholder-slate-500 rounded-xl px-4 py-2.5 text-sm
                     outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500/50
                     disabled:opacity-50 transition-all"
        />
        <button
          onClick={() => askQuestion()}
          disabled={loading || !question.trim()}
          className="bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed
                     text-white px-4 py-2.5 rounded-xl transition-all shadow-lg shadow-blue-900/20
                     flex items-center justify-center"
        >
          <Send size={15} />
        </button>
      </div>
    </div>
  )
}