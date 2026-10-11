import { useEffect, useState } from 'react'
import { api } from '../api'
import { Empty, PageHead } from '../ui'

const HUES = ['#0a84ff', '#30b0c7', '#34c759', '#ff9f0a', '#ff375f', '#bf5af2', '#5e5ce6']
const hue = (s) => HUES[[...s].reduce((a, c) => a + c.charCodeAt(0), 0) % HUES.length]

export default function Agents() {
  const [agents, setAgents] = useState([])
  useEffect(() => { api('/marketplace/agents').then((d) => setAgents(Array.isArray(d) ? d : d.agents || [])).catch(() => {}) }, [])
  return (
    <div className="page">
      <PageHead title="Agents" subtitle="The specialists the planner can assign tasks to." />
      {agents.length === 0 ? <div className="card"><Empty title="No agents found">Start the API server to see registered agents.</Empty></div>
        : <div className="agent-grid">{agents.map((a) => (
          <div className="card agent-card" key={a.name}>
            <div className="agent-avatar" style={{ background: hue(a.name) }}>{a.name[0].toUpperCase()}</div>
            <div><div className="row-title" style={{ textTransform: 'capitalize' }}>{a.name}</div><p className="muted" style={{ fontSize: 14, marginTop: 4 }}>{a.description}</p></div>
            <div className="tags">{(a.capabilities || []).map((c, i) => <span key={i} className="badge">{String(typeof c === 'string' ? c : c.capability).replace(/_/g, ' ')}</span>)}</div>
          </div>))}</div>}
    </div>
  )
}
