import { useEffect, useState } from 'react'
import { api } from '../api'
import DAGGraph from '../components/DAGGraph'
import MetricsDashboard from '../components/MetricsDashboard'
import { Empty, PageHead, Segmented } from '../ui'

export default function Insights() {
  const [tab, setTab] = useState('plan')
  const [sessions, setSessions] = useState([])
  const [sid, setSid] = useState('')
  const [tasks, setTasks] = useState([])
  useEffect(() => { api('/sessions').then((d) => { const ids = Object.keys(d.sessions || {}).reverse(); setSessions(ids); setSid((s) => s || ids[0] || '') }).catch(() => {}) }, [])
  useEffect(() => { if (sid) api(`/status/${sid}`).then((d) => setTasks(d.plan?.tasks || [])).catch(() => setTasks([])) }, [sid])
  return (
    <div className="page">
      <PageHead title="Insights" subtitle="See how a goal was broken down, and how your agents are performing."
        actions={<Segmented value={tab} onChange={setTab} options={[{ value: 'plan', label: 'Plan' }, { value: 'metrics', label: 'Metrics' }]} />} />
      {tab === 'metrics' ? <MetricsDashboard /> : sessions.length === 0
        ? <div className="card"><Empty title="No runs yet">Run a goal and its task graph will show up here.</Empty></div>
        : <>
          <div style={{ marginBottom: 14, display: 'flex', alignItems: 'center', gap: 10 }}>
            <span className="label">Run</span>
            <select className="select" style={{ width: 'auto', minWidth: 260 }} value={sid} onChange={(e) => setSid(e.target.value)}>
              {sessions.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          {tasks.length ? <DAGGraph tasks={tasks} /> : <div className="card"><Empty title="No plan saved for this run">Plans are kept in memory while the server runs.</Empty></div>}
        </>}
    </div>
  )
}
