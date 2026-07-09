import { useState } from "react"
import axios from "axios"
import { MessageCircle, Send, Loader } from "lucide-react"

export default function ChatInterface() {
  const [question, setQuestion] = useState("")
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)

  const askQuestion = async () => {
    if (!question.trim() || loading) return

    const userQuestion = question
    setQuestion("")
    setMessages(prev => [...prev, {
      role: "user",
      content: userQuestion
    }])
    setLoading(true)

    try {
      const response = await axios.post(
        "http://localhost:8000/chat/ask",
        { question: userQuestion }
      )
      setMessages(prev => [...prev, {
        role: "assistant",
        content: response.data.answer
      }])
    } catch (error) {
      setMessages(prev => [...prev, {
        role: "assistant",
        content: "Sorry, I couldn't process that question. Make sure the backend is running."
      }])
    } finally {
      setLoading(false)
    }
  }

  const handleKeyPress = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      askQuestion()
    }
  }

  return (
    <div className="bg-slate-800 rounded-xl p-6 text-white">
      <div className="flex items-center gap-2 mb-4">
        <MessageCircle className="text-blue-400" size={20} />
        <h2 className="text-xl font-bold">Ask SentinelAI</h2>
      </div>

      {/* Messages */}
      <div className="space-y-3 mb-4 max-h-96 overflow-y-auto">
        {messages.length === 0 && (
          <div className="text-slate-400 text-sm">
            <p className="mb-2">Ask me anything about your system. For example:</p>
            <ul className="space-y-1 text-slate-500">
              <li>→ "When did my RAM last spike?"</li>
              <li>→ "What processes have been using the most CPU?"</li>
              <li>→ "Is my system behaving normally?"</li>
              <li>→ "What was running at 3 AM?"</li>
            </ul>
          </div>
        )}

        {messages.map((msg, idx) => (
          <div key={idx} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-xs lg:max-w-md px-4 py-2 rounded-lg text-sm ${
              msg.role === "user"
                ? "bg-blue-600 text-white"
                : "bg-slate-700 text-slate-200"
            }`}>
              {msg.content}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-slate-700 px-4 py-2 rounded-lg flex items-center gap-2 text-sm text-slate-400">
              <Loader size={14} className="animate-spin" />
              Analyzing your system data...
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="flex gap-2">
        <input
          type="text"
          value={question}
          onChange={e => setQuestion(e.target.value)}
          onKeyPress={handleKeyPress}
          placeholder="Ask about your system..."
          className="flex-1 bg-slate-700 text-white rounded-lg px-4 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button
          onClick={askQuestion}
          disabled={loading || !question.trim()}
          className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 px-4 py-2 rounded-lg transition"
        >
          <Send size={16} />
        </button>
      </div>
    </div>
  )
}