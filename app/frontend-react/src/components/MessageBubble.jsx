import { marked } from 'marked'
import DOMPurify from 'dompurify'

marked.setOptions({
  breaks: true,
  gfm: true,
})

function renderMarkdown(content) {
  const html = marked.parse(content)
  return DOMPurify.sanitize(html)
}

export default function MessageBubble({ message }) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[80%] rounded-xl px-4 py-3 ${
        isUser
          ? 'bg-[var(--accent)] text-white'
          : 'glass'
      }`}>
        {isUser ? (
          <p className="text-sm whitespace-pre-wrap">{message.content}</p>
        ) : (
          <div
            className="text-sm prose prose-invert prose-sm max-w-none"
            dangerouslySetInnerHTML={{ __html: renderMarkdown(message.content || '') }}
          />
        )}
        {message.extra?.model && (
          <div className="mt-2 pt-2 border-t border-white/10 text-xs opacity-60">
            {message.extra.model}
          </div>
        )}
      </div>
    </div>
  )
}
