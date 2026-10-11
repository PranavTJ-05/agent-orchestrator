import { useEffect, useState } from 'react'
import { api } from '../api'
import { Empty, PageHead, Segmented } from '../ui'

const KIND = (t) => (t.includes('failed') ? 'red' : t.includes('completed') ? 'green' : t.includes('started') ? 'blue' : '')
const when = (ts) => (ts ? new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '')

export default function Activity() {
  const [events, setEvents] = useState([])
  const [types, setTypes] = useState([])
  const [filter, setFilter] = useState('all')
  useEffect(() => {
    api('/events/types').then(setTypes).catch(() => {})
    const load = () => api('/events?limit=200').then((d) => setEvents(Array.isArray(d) ? d : d.events || [])).catch(() => {})
    load(); const t = setInterval(load, 4000); return () => clearInterval(t)
  }, [])
  const groups = [{ value: 'all', label: 'All' }, { value: 'task', label: 'Tasks' }, { value: 'session', label: 'Sessions' }, { value: 'wave', label: 'Waves' }]
  const shown = events.filter((e) => filter === 'all' || String(e.type).includes(filter)).slice().reverse().slice(0, 100)
  return (
    <div className="page">
      <PageHead title="Activity" subtitle="Everything the orchestrator did, newest first." actions={<Segmented value={filter} onChange={setFilter} options={groups} />} />
      {shown.length === 0
        ? <div className="card"><Empty title="No activity yet">Run a goal and its tasks and agents will appear here.{types.length ? ` (${types.length} event types tracked)` : ''}</Empty></div>
        : <div className="group">{shown.map((e, i) => {
            const d = e.data || e
            return (
              <div className="row" key={i} style={{ minHeight: 48, padding: '10px 18px' }}>
                <span className={`badge ${KIND(String(e.type))}`} style={{ minWidth: 118, justifyContent: 'center' }}>{String(e.type).replace(/_/g, ' ')}</span>
                <div className="row-main"><div className="row-sub" style={{ color: 'var(--text)' }}>{d.task_description || d.goal || d.agent_name || d.agent || ''}</div>
                  {(d.agent || d.error) && <div className="row-sub">{[d.agent && `agent: ${d.agent}`, d.error].filter(Boolean).join(' · ')}</div>}</div>
                <span className="caption" style={{ fontVariantNumeric: 'tabular-nums' }}>{when(e.timestamp)}</span>
              </div>)})}</div>}
    </div>
  )
}
