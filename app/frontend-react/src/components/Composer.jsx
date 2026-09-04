import { useRef, useEffect } from 'react'
import gsap from 'gsap'

export default function Composer({ input, setInput, onSubmit, loading }) {
  const sendRef = useRef(null)
  const textareaRef = useRef(null)

  useEffect(() => {
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduced || !sendRef.current) return

    const btn = sendRef.current
    const strength = 12

    const onMove = (e) => {
      const rect = btn.getBoundingClientRect()
      const x = e.clientX - rect.left - rect.width / 2
      const y = e.clientY - rect.top - rect.height / 2
      gsap.to(btn, { x: x * 0.3, y: y * 0.3, duration: 0.3, ease: 'power3' })
    }
    const onLeave = () => {
      gsap.to(btn, { x: 0, y: 0, duration: 0.5, ease: 'elastic.out(1, 0.5)' })
    }

    btn.addEventListener('mousemove', onMove)
    btn.addEventListener('mouseleave', onLeave)
    return () => {
      btn.removeEventListener('mousemove', onMove)
      btn.removeEventListener('mouseleave', onLeave)
    }
  }, [])

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSubmit()
    }
  }

  const handleInput = (e) => {
    setInput(e.target.value)
    // Auto-resize textarea
    const ta = e.target
    ta.style.height = 'auto'
    ta.style.height = Math.min(ta.scrollHeight, 128) + 'px'
  }

  return (
    <div className="px-6 pb-6">
      <div className="max-w-3xl mx-auto">
        <div
          className="composer rounded-xl flex items-end gap-2 p-2"
          style={{
            background: 'var(--panel)',
            border: '1px solid var(--border)',
            backdropFilter: 'blur(12px)',
          }}
        >
          <textarea
            ref={textareaRef}
            value={input}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question..."
            className="flex-1 bg-transparent resize-none outline-none px-3 py-2 text-sm"
            style={{ color: 'var(--text)', maxHeight: '128px' }}
            rows={1}
            disabled={loading}
          />
          <button
            ref={sendRef}
            onClick={onSubmit}
            disabled={!input.trim() || loading}
            className="w-9 h-9 rounded-lg flex items-center justify-center text-sm font-medium transition-all duration-150 shrink-0"
            style={{
              background: input.trim() && !loading ? 'var(--text)' : 'var(--panel)',
              color: input.trim() && !loading ? 'var(--bg)' : 'var(--text-faint)',
              cursor: input.trim() && !loading ? 'pointer' : 'not-allowed',
            }}
            onMouseEnter={e => {
              if (input.trim() && !loading) {
                e.currentTarget.style.animation = 'softGlow 1.8s ease-in-out infinite'
              }
            }}
            onMouseLeave={e => {
              e.currentTarget.style.animation = 'none'
            }}
          >
            {loading ? (
              <span className="typing-dots">
                <span /><span /><span />
              </span>
            ) : (
              <span style={{ display: 'inline-block', transform: 'rotate(-45deg)', marginTop: '2px' }}>→</span>
            )}
          </button>
        </div>
        <p className="text-center text-xs mt-2" style={{ color: 'var(--text-faint)' }}>
          Press Enter to send, Shift+Enter for new line
        </p>
      </div>
    </div>
  )
}
