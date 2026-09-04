import { useEffect, useRef } from 'react'
import Hero from './Hero'
import MessageBubble from './MessageBubble'
import Composer from './Composer'

export default function ChatArea({ messages, onSend, loading, conversation, input, setInput }) {
  const messagesEndRef = useRef(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  return (
    <div className="flex-1 flex flex-col h-screen relative z-10">
      {/* Header */}
      <div
        className="flex items-center justify-between px-6 py-4 shrink-0"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <h2 className="font-medium truncate" style={{ color: 'var(--text)' }}>
          {conversation?.title || 'New Chat'}
        </h2>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center">
            <Hero />
            <p className="text-sm" style={{ color: 'var(--text-dim)' }}>
              Ask me anything about your research
            </p>
          </div>
        ) : (
          <div className="max-w-3xl mx-auto space-y-6">
            {messages.map((msg, i) => (
              <MessageBubble key={msg.id} message={msg} animate={i === messages.length - 1} />
            ))}
            {loading && messages[messages.length - 1]?.role === 'assistant' && messages[messages.length - 1]?.content === '' && (
              <div className="flex justify-start">
                <div
                  className="rounded-xl px-4 py-3"
                  style={{ background: 'var(--assistant-bg)', border: '1px solid var(--border)' }}
                >
                  <div className="flex items-center gap-2">
                    <span className="thinking-dot" />
                    <span className="text-sm" style={{ color: 'var(--text-dim)' }}>Thinking...</span>
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Composer */}
      <Composer
        input={input}
        setInput={setInput}
        onSubmit={() => { if (input.trim()) { onSend(input.trim()); setInput('') } }}
        loading={loading}
      />
    </div>
  )
}
