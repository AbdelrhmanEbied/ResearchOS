import { useEffect, useRef } from 'react'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import gsap from 'gsap'

marked.setOptions({ breaks: true, gfm: true })

function renderMarkdown(content) {
  return DOMPurify.sanitize(marked.parse(content))
}

function Typewriter({ content }) {
  const ref = useRef(null)
  const shownRef = useRef(0)
  const rafRef = useRef(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduced) {
      el.innerHTML = renderMarkdown(content)
      return
    }

    const target = content
    const tick = () => {
      const backlog = target.length - shownRef.current
      shownRef.current = Math.min(target.length, shownRef.current + Math.max(2, Math.ceil(backlog / 8)))
      const html = renderMarkdown(target.substring(0, shownRef.current))
      el.innerHTML = html

      if (shownRef.current < target.length) {
        // Add caret
        const lastBlock = el.querySelector('p:last-child, li:last-child, pre:last-child code, td:last-child')
        if (lastBlock) {
          const caret = document.createElement('span')
          caret.className = 'caret'
          lastBlock.appendChild(caret)
        }
        rafRef.current = requestAnimationFrame(tick)
      }
    }

    shownRef.current = 0
    rafRef.current = requestAnimationFrame(tick)

    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current) }
  }, [content])

  return <div ref={ref} className="text-sm leading-relaxed" style={{ color: 'var(--text)' }} />
}

export default function MessageBubble({ message, animate = true }) {
  const rowRef = useRef(null)
  const isUser = message.role === 'user'

  useEffect(() => {
    if (!animate || !rowRef.current) return
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduced) return

    gsap.from(rowRef.current, {
      opacity: 0, y: 22, scale: 0.97,
      duration: 0.5, ease: 'back.out(1.5)',
    })
  }, [animate])

  return (
    <div ref={rowRef} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className="max-w-[80%] rounded-xl px-4 py-3 transition-colors duration-400"
        style={{
          background: isUser ? 'var(--text)' : 'var(--assistant-bg)',
          color: isUser ? 'var(--bg)' : 'var(--text)',
          border: isUser ? 'none' : '1px solid var(--border)',
        }}
      >
        {isUser ? (
          <p className="text-sm whitespace-pre-wrap">{message.content}</p>
        ) : (
          <>
            {!message.content && (
              <div className="flex items-center gap-2 py-1">
                <span className="thinking-dot" />
                <span className="text-sm" style={{ color: 'var(--text-dim)' }}>Thinking...</span>
              </div>
            )}
            {message.content && <Typewriter content={message.content} />}
          </>
        )}
        {message.extra?.model && (
          <div
            className="mt-2 pt-2 text-xs"
            style={{ borderTop: '1px solid var(--border)', color: 'var(--text-faint)' }}
          >
            {message.extra.model}
          </div>
        )}
      </div>
    </div>
  )
}
