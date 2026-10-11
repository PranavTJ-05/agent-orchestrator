import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api'

const Ctx = createContext(null)
export const useStudio = () => useContext(Ctx)

/** Shared, live Studio state: servers, tools, approvals and the event stream (SSE). */
export function StudioProvider({ children, toast }) {
  const [servers, setServers] = useState([])
  const [tools, setTools] = useState([])
  const [status, setStatus] = useState(null)
  const [approvals, setApprovals] = useState([])
  const [events, setEvents] = useState([])
  const [online, setOnline] = useState(true)
  const listeners = useRef(new Set())

  const refresh = useCallback(async () => {
    try {
      const [s, t, st, a] = await Promise.all([
        api('/studio/servers'), api('/studio/tools'), api('/studio/status'), api('/studio/approvals'),
      ])
      setServers(s); setTools(t); setStatus(st); setApprovals(a); setOnline(true)
    } catch { setOnline(false) }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  useEffect(() => {
    let es, retry, closed = false
    const open = () => {
      es = new EventSource('/api/studio/events')
      es.onopen = () => setOnline(true)
      es.onmessage = (m) => {
        const ev = JSON.parse(m.data)
        setEvents((prev) => [ev, ...prev].slice(0, 200))
        if (ev.type === 'server_changed' || ev.type === 'server_removed') refresh()
        if (ev.type === 'approval_requested') setApprovals((p) => (p.some((x) => x.id === ev.id) ? p : [...p, ev]))
        if (ev.type === 'approval_resolved') setApprovals((p) => p.filter((x) => x.id !== ev.id))
        listeners.current.forEach((fn) => fn(ev))
      }
      es.onerror = () => { es.close(); if (!closed) retry = setTimeout(open, 3000) }
    }
    open()
    return () => { closed = true; clearTimeout(retry); es?.close() }
  }, [refresh])

  const subscribe = useCallback((fn) => { listeners.current.add(fn); return () => listeners.current.delete(fn) }, [])
  const decide = useCallback(async (id, approve) => {
    try { await api(`/studio/approvals/${id}`, { method: 'POST', body: { approve } }) }
    catch (e) { toast?.(e.message, 'error') }
    setApprovals((p) => p.filter((x) => x.id !== id))
  }, [toast])

  const value = useMemo(() => ({ servers, tools, status, approvals, events, online, refresh, subscribe, decide }),
    [servers, tools, status, approvals, events, online, refresh, subscribe, decide])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
