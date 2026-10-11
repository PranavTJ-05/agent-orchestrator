import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import { Empty } from '../ui'

const tip = { contentStyle: { background: 'var(--surface)', border: '0.5px solid var(--sep)', borderRadius: 12, boxShadow: 'var(--shadow-card)', fontSize: 13 }, cursor: { fill: 'var(--fill-2)' } }

export default function MetricsDashboard() {
  const [cost, setCost] = useState(null)
  const [evalData, setEvalData] = useState(null)
  const [board, setBoard] = useState([])
  useEffect(() => {
    api('/cost/summary').then(setCost).catch(() => {})
    api('/evaluation/summary').then(setEvalData).catch(() => {})
    api('/evaluation/leaderboard').then((d) => setBoard(d.leaderboard || (Array.isArray(d) ? d : []))).catch(() => {})
  }, [])
  const rate = evalData?.avg_success_rate
  const byModel = Object.entries(cost?.by_model || {}).map(([model, v]) => ({ model, cost: Number(v) }))
  return (
    <>
      <div className="stats">
        <div className="card stat"><div className="stat-label">Tokens used</div><div className="stat-value">{(cost?.total_tokens ?? 0).toLocaleString()}</div><div className="stat-sub">${(cost?.total_cost ?? 0).toFixed(4)} estimated</div></div>
        <div className="card stat"><div className="stat-label">Tasks run</div><div className="stat-value">{evalData?.total_tasks ?? 0}</div><div className="stat-sub">evaluated</div></div>
        <div className="card stat"><div className="stat-label">Success rate</div><div className="stat-value">{rate == null ? '—' : `${(rate * 100).toFixed(0)}%`}</div><div className="stat-sub">across agents</div></div>
      </div>
      <div className="section">
        <div className="section-head"><span className="section-title">Agent success rate</span></div>
        <div className="card card-pad">
          {board.length ? (
            <ResponsiveContainer width="100%" height={Math.max(160, board.slice(0, 8).length * 44)}>
              <BarChart data={board.slice(0, 8)} layout="vertical" margin={{ left: 20, right: 12 }}>
                <CartesianGrid horizontal={false} stroke="var(--sep)" />
                <XAxis type="number" domain={[0, 1]} tickFormatter={(v) => `${v * 100}%`} stroke="var(--text-3)" fontSize={12} tickLine={false} axisLine={false} />
                <YAxis dataKey="agent_name" type="category" stroke="var(--text-2)" fontSize={13} tickLine={false} axisLine={false} width={90} />
                <Tooltip {...tip} formatter={(v) => `${(v * 100).toFixed(0)}%`} />
                <Bar dataKey="success_rate" fill="var(--accent)" radius={[0, 8, 8, 0]} barSize={18} />
              </BarChart>
            </ResponsiveContainer>) : <Empty title="No data yet">Agent results appear after your first run.</Empty>}
        </div>
      </div>
      {byModel.length > 0 && <div className="section">
        <div className="section-head"><span className="section-title">Cost by model</span></div>
        <div className="card card-pad"><ResponsiveContainer width="100%" height={200}>
          <BarChart data={byModel}><CartesianGrid vertical={false} stroke="var(--sep)" />
            <XAxis dataKey="model" stroke="var(--text-3)" fontSize={12} tickLine={false} axisLine={false} />
            <YAxis stroke="var(--text-3)" fontSize={12} tickLine={false} axisLine={false} /><Tooltip {...tip} />
            <Bar dataKey="cost" fill="var(--green)" radius={[8, 8, 0, 0]} barSize={36} /></BarChart></ResponsiveContainer></div>
      </div>}
    </>
  )
}
