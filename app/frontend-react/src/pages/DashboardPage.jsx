import { useState, useEffect, useRef } from 'react'
import { useAuth } from '../context/AuthContext'
import { apiGet, apiPost, apiPatch, apiDelete, apiStream } from '../api/client'
import Sidebar from '../components/Sidebar'
import ChatArea from '../components/ChatArea'

export default function DashboardPage() {
  const { user, logout } = useAuth()
  const [conversations, setConversations] = useState([])
  const [activeId, setActiveId] = useState(null)
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    loadConversations()
  }, [])

  useEffect(() => {
    if (activeId) {
      loadMessages(activeId)
    }
  }, [activeId])

  const loadConversations = async () => {
    try {
      const data = await apiGet('/chat/list')
      setConversations(data)
      if (data.length > 0 && !activeId) {
        setActiveId(data[0].id)
      }
    } catch (err) {
      console.error('Failed to load conversations:', err)
    }
  }

  const loadMessages = async (convId) => {
    try {
      const data = await apiGet(`/chat/${convId}/messages?limit=200`)
      setMessages(data.messages.reverse())
    } catch (err) {
      console.error('Failed to load messages:', err)
    }
  }

  const createConversation = async () => {
    try {
      const conv = await apiPost('/chat/conversations', {})
      setConversations(prev => [conv, ...prev])
      setActiveId(conv.id)
      setMessages([])
    } catch (err) {
      console.error('Failed to create conversation:', err)
    }
  }

  const deleteConversation = async (convId) => {
    try {
      await apiDelete(`/chat/${convId}`)
      setConversations(prev => prev.filter(c => c.id !== convId))
      if (activeId === convId) {
        setActiveId(conversations.find(c => c.id !== convId)?.id || null)
        setMessages([])
      }
    } catch (err) {
      console.error('Failed to delete conversation:', err)
    }
  }

  const renameConversation = async (convId, title) => {
    try {
      const updated = await apiPatch(`/chat/${convId}`, { title })
      setConversations(prev => prev.map(c => c.id === convId ? { ...c, title: updated.title } : c))
    } catch (err) {
      console.error('Failed to rename conversation:', err)
    }
  }

  const sendMessage = async (query) => {
    if (!activeId || loading) return

    const userMsg = { id: Date.now(), role: 'user', content: query, created_at: new Date().toISOString() }
    setMessages(prev => [...prev, userMsg])
    setLoading(true)

    const assistantMsg = { id: Date.now() + 1, role: 'assistant', content: '', created_at: new Date().toISOString(), extra: null }
    setMessages(prev => [...prev, assistantMsg])

    try {
      let extra = null

      const buffer = await apiStream('/chat/', {
        query,
        conversation_id: activeId,
        agent_mode: 'fast',
      }, (chunk) => {
        const sourcesMarker = '@@RESEARCH_SOURCES@@'
        const thinkingMarker = '@@RESEARCH_THINKING@@'
        const errorMarker = '@@RESEARCH_ERROR@@'

        let clean = chunk

        const thinkingIdx = clean.indexOf(thinkingMarker)
        if (thinkingIdx !== -1) {
          const afterThinking = clean.indexOf(thinkingMarker, thinkingIdx + thinkingMarker.length)
          if (afterThinking !== -1) {
            clean = clean.substring(afterThinking + thinkingMarker.length)
          }
        }

        const sourcesIdx = clean.indexOf(sourcesMarker)
        if (sourcesIdx !== -1) {
          clean = clean.substring(0, sourcesIdx)
        }

        const errorIdx = clean.indexOf(errorMarker)
        if (errorIdx !== -1) {
          clean = clean.substring(0, errorIdx)
        }

        const detailsMarker = '@@RESEARCH_DETAILS@@'
        const detailsIdx2 = clean.indexOf(detailsMarker)
        const text = detailsIdx2 !== -1 ? clean.substring(0, detailsIdx2) : clean

        setMessages(prev => prev.map(m => m.id === assistantMsg.id ? { ...m, content: text.trim() } : m))
      })

      const detailsIdx = buffer.indexOf('@@RESEARCH_DETAILS@@')
      if (detailsIdx !== -1) {
        try {
          const afterDetails = buffer.substring(detailsIdx + '@@RESEARCH_DETAILS@@'.length)
          const endIdx = afterDetails.indexOf('@@')
          const jsonStr = endIdx !== -1 ? afterDetails.substring(0, endIdx).trim() : afterDetails.trim()
          extra = JSON.parse(jsonStr)
        } catch {}
      }

      const sourcesIdx = buffer.indexOf('@@RESEARCH_SOURCES@@')
      let sources = null
      if (sourcesIdx !== -1) {
        try {
          const afterSources = buffer.substring(sourcesIdx + '@@RESEARCH_SOURCES@@'.length)
          const endIdx = afterSources.indexOf('@@')
          const jsonStr = endIdx !== -1 ? afterSources.substring(0, endIdx).trim() : afterSources.trim()
          sources = JSON.parse(jsonStr)
        } catch {}
      }

      setMessages(prev => prev.map(m => m.id === assistantMsg.id ? { ...m, extra: { ...extra, sources } } : m))

      loadConversations()
    } catch (err) {
      console.error('Failed to send message:', err)
      setMessages(prev => prev.map(m => m.id === assistantMsg.id ? { ...m, content: 'Failed to get response. Please try again.' } : m))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex h-screen">
      <Sidebar
        conversations={conversations}
        activeId={activeId}
        onSelect={setActiveId}
        onNew={createConversation}
        onDelete={deleteConversation}
        onRename={renameConversation}
        user={user}
        onLogout={logout}
      />
      <ChatArea
        messages={messages}
        onSend={sendMessage}
        loading={loading}
        conversation={conversations.find(c => c.id === activeId)}
      />
    </div>
  )
}
