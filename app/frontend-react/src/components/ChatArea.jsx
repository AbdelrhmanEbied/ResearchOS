import { useState, useRef, useEffect } from 'react'
import MessageBubble from './MessageBubble'

export default function ChatArea({ messages, onSend, loading, conversation }) {
  const [input, setInput] = useState('')
  const messagesEndRef = useRef(null)
  const textareaRef = useRef(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!input.trim() || loading) return
    onSend(input.trim())
    setInput('')
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  return (
    <div className="flex-1 flex flex-col h-screen">
      <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--border-color)]">
        <h2 className="font-medium truncate">
          {conversation?.title || 'New Chat'}
        </h2>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-4">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center">
            <h1 className="text-4xl font-serif font-bold mb-3">How can I help you today?</h1>
            <p className="text-[var(--text-secondary)]">Ask me anything about your research</p>
          </div>
        ) : (
          <div className="max-w-3xl mx-auto space-y-6">
            {messages.map(msg => (
              <MessageBubble key={msg.id} message={msg} />
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      <div className="px-6 pb-6">
        <form onSubmit={handleSubmit} className="max-w-3xl mx-auto">
          <div className="glass rounded-xl flex items-end gap-2 p-2">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask a question..."
              className="flex-1 bg-transparent resize-none outline-none px-3 py-2 text-sm max-h-32"
              rows={1}
              disabled={loading}
            />
            <button
              type="submit"
              disabled={!input.trim() || loading}
              className="btn-primary px-4 py-2 text-sm"
            >
              {loading ? '...' : '→'}
            </button>
          </div>
          <p className="text-center text-xs text-[var(--text-secondary)] mt-2">
            Press Enter to send, Shift+Enter for new line
          </p>
        </form>
      </div>
    </div>
  )
}
