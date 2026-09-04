import { useState } from 'react'
import ThemeToggle from './ThemeToggle'

export default function Sidebar({ conversations, activeId, onSelect, onNew, onDelete, onRename, user, onLogout }) {
  const [search, setSearch] = useState('')
  const [editingId, setEditingId] = useState(null)
  const [editTitle, setEditTitle] = useState('')

  const filtered = conversations.filter(c =>
    !search || c.title?.toLowerCase().includes(search.toLowerCase())
  )

  const startRename = (conv) => {
    setEditingId(conv.id)
    setEditTitle(conv.title || '')
  }

  const submitRename = () => {
    if (editTitle.trim() && editingId) {
      onRename(editingId, editTitle.trim())
    }
    setEditingId(null)
  }

  return (
    <aside
      className="w-64 h-screen flex flex-col shrink-0"
      style={{
        background: 'var(--panel)',
        backdropFilter: 'blur(24px) saturate(120%)',
        WebkitBackdropFilter: 'blur(24px) saturate(120%)',
        borderRight: '1px solid var(--border)',
      }}
    >
      {/* Header */}
      <div className="p-4" style={{ borderBottom: '1px solid var(--border)' }}>
        <button
          onClick={onNew}
          className="w-full py-2 px-4 rounded-lg text-sm font-medium transition-all duration-180"
          style={{
            background: 'var(--panel)',
            border: '1px solid var(--border)',
            color: 'var(--text)',
          }}
          onMouseEnter={e => { e.target.style.background = 'var(--panel-strong)'; e.target.style.borderColor = 'var(--border-strong)' }}
          onMouseLeave={e => { e.target.style.background = 'var(--panel)'; e.target.style.borderColor = 'var(--border)' }}
        >
          + New chat
        </button>
      </div>

      {/* Search */}
      <div className="px-3 py-2">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search chats..."
          className="input-field text-sm py-2"
        />
      </div>

      {/* Conversations */}
      <div className="flex-1 overflow-y-auto px-2">
        <div
          className="text-xs font-medium px-2 py-1 uppercase tracking-wide"
          style={{ color: 'var(--text-faint)' }}
        >
          Chats
        </div>
        {filtered.map(conv => (
          <div
            key={conv.id}
            onClick={() => onSelect(conv.id)}
            className="group flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-all duration-150"
            style={{
              background: activeId === conv.id ? 'var(--panel-strong)' : 'transparent',
              color: activeId === conv.id ? 'var(--text)' : 'var(--text-dim)',
            }}
            onMouseEnter={e => { if (activeId !== conv.id) e.currentTarget.style.background = 'var(--panel)' }}
            onMouseLeave={e => { if (activeId !== conv.id) e.currentTarget.style.background = 'transparent' }}
          >
            {editingId === conv.id ? (
              <input
                value={editTitle}
                onChange={(e) => setEditTitle(e.target.value)}
                onBlur={submitRename}
                onKeyDown={(e) => e.key === 'Enter' && submitRename()}
                className="flex-1 bg-transparent text-sm outline-none"
                style={{ color: 'var(--text)' }}
                autoFocus
                onClick={(e) => e.stopPropagation()}
              />
            ) : (
              <span className="flex-1 text-sm truncate">{conv.title || 'New Chat'}</span>
            )}
            <div className="hidden group-hover:flex gap-1">
              <button
                onClick={(e) => { e.stopPropagation(); startRename(conv) }}
                className="text-xs p-1 rounded transition-colors duration-150"
                style={{ color: 'var(--text-faint)' }}
                onMouseEnter={e => e.target.style.color = 'var(--text)'}
                onMouseLeave={e => e.target.style.color = 'var(--text-faint)'}
              >
                ✏️
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); onDelete(conv.id) }}
                className="text-xs p-1 rounded transition-colors duration-150"
                style={{ color: 'var(--text-faint)' }}
                onMouseEnter={e => { e.target.style.color = 'var(--danger)'; e.target.style.background = 'rgba(229,100,95,0.12)' }}
                onMouseLeave={e => { e.target.style.color = 'var(--text-faint)'; e.target.style.background = 'transparent' }}
              >
                🗑️
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="p-3" style={{ borderTop: '1px solid var(--border)' }}>
        <div className="flex items-center justify-between mb-2">
          <ThemeToggle />
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm truncate" style={{ color: 'var(--text-dim)' }}>{user?.email}</span>
          <button
            onClick={onLogout}
            className="text-xs transition-colors duration-150"
            style={{ color: 'var(--text-faint)' }}
            onMouseEnter={e => e.target.style.color = 'var(--danger)'}
            onMouseLeave={e => e.target.style.color = 'var(--text-faint)'}
          >
            Logout
          </button>
        </div>
      </div>
    </aside>
  )
}
