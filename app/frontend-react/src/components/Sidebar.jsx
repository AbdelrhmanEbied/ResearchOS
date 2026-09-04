import { useState } from 'react'

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
    <div className="w-64 h-screen flex flex-col glass border-r border-[var(--border-color)]">
      <div className="p-4 border-b border-[var(--border-color)]">
        <button onClick={onNew} className="btn-primary w-full text-sm py-2">
          + New chat
        </button>
      </div>

      <div className="p-3">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search chats..."
          className="input-field text-sm py-2"
        />
      </div>

      <div className="flex-1 overflow-y-auto px-2">
        <div className="text-xs font-medium text-[var(--text-secondary)] px-2 py-1 uppercase tracking-wide">
          Chats
        </div>
        {filtered.map(conv => (
          <div
            key={conv.id}
            onClick={() => onSelect(conv.id)}
            className={`group flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-colors ${
              activeId === conv.id
                ? 'bg-[var(--accent)]/10 text-[var(--accent)]'
                : 'hover:bg-white/5 text-[var(--text-secondary)]'
            }`}
          >
            {editingId === conv.id ? (
              <input
                value={editTitle}
                onChange={(e) => setEditTitle(e.target.value)}
                onBlur={submitRename}
                onKeyDown={(e) => e.key === 'Enter' && submitRename()}
                className="flex-1 bg-transparent text-sm outline-none"
                autoFocus
                onClick={(e) => e.stopPropagation()}
              />
            ) : (
              <span className="flex-1 text-sm truncate">{conv.title || 'New Chat'}</span>
            )}
            <div className="hidden group-hover:flex gap-1">
              <button
                onClick={(e) => { e.stopPropagation(); startRename(conv) }}
                className="text-[var(--text-secondary)] hover:text-white text-xs p-1"
              >
                ✏️
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); onDelete(conv.id) }}
                className="text-[var(--text-secondary)] hover:text-red-400 text-xs p-1"
              >
                🗑️
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className="p-3 border-t border-[var(--border-color)]">
        <div className="flex items-center justify-between">
          <span className="text-sm text-[var(--text-secondary)] truncate">{user?.email}</span>
          <button
            onClick={onLogout}
            className="text-xs text-[var(--text-secondary)] hover:text-red-400 transition-colors"
          >
            Logout
          </button>
        </div>
      </div>
    </div>
  )
}
