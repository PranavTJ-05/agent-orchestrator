import { useEffect, useState } from 'react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts'

const COLORS = ['#58a6ff', '#238636', '#f85149', '#f0883e', '#a371f7', '#3fb950']

export default function MetricsDashboard() {
  const [costData, setCostData] = useState(null)
  const [evalData, setEvalData] = useState(null)
  const [leaderboard, setLeaderboard] = useState([])

  useEffect(() => {
    fetch('/api/cost/summary').then(r => r.json()).then(d => setCostData(d))
    fetch('/api/evaluation/leaderboard').then(r => r.json()).then(d => setLeaderboard(d.leaderboard || []))
    fetch('/api/evaluation/summary').then(r => r.json()).then(d => setEvalData(d))
  }, [])

  return (
    <div className="metrics-grid">
      <MetricCard title="Total Cost" value={`$${costData?.total_cost?.toFixed(4) || '0.0000'}`} sub={`${costData?.total_tokens || 0} tokens`} />
      <MetricCard title="Total Sessions" value={costData?.sessions?.length || 0} sub="completed" />
      <MetricCard title="Avg Success Rate" value={`${(evalData?.avg_success_rate * 100)?.toFixed(1) || 0}%`} sub="agent tasks" />
      <MetricCard title="Total Tasks" value={evalData?.total_tasks || 0} sub="evaluated" />

      <div className="metric-card" style={{ gridColumn: 'span 2' }}>
        <h3>Agent Leaderboard</h3>
        {leaderboard.length > 0 ? (
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={leaderboard.slice(0, 8)} layout="vertical" margin={{ left: 80 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#21262d" />
              <XAxis type="number" stroke="#8b949e" />
              <YAxis dataKey="agent_name" type="category" stroke="#8b949e" />
              <Tooltip contentStyle={{ background: '#161b22', border: '1px solid #21262d' }} />
              <Bar dataKey="success_rate" fill="#58a6ff" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <p style={{ color: '#8b949e', padding: 40, textAlign: 'center' }}>No evaluation data yet</p>
        )}
      </div>

      <div className="metric-card">
        <h3>Task Status Distribution</h3>
        <ResponsiveContainer width="100%" height={250}>
          <PieChart>
            <Pie
              data={[
                { name: 'Pending', value: costData?.sessions?.filter(s => s.status === 'pending')?.length || 0 },
                { name: 'Running', value: costData?.sessions?.filter(s => s.status === 'running')?.length || 0 },
                { name: 'Completed', value: costData?.sessions?.filter(s => s.status === 'completed')?.length || 0 },
                { name: 'Failed', value: costData?.sessions?.filter(s => s.status === 'failed')?.length || 0 },
              ]}
              cx="50%" cy="50%" innerRadius={40} outerRadius={80}
              dataKey="value"
              label
            >
              {COLORS.map((c, i) => <Cell key={i} fill={c} />)}
            </Pie>
            <Tooltip contentStyle={{ background: '#161b22', border: '1px solid #21262d' }} />
          </PieChart>
        </ResponsiveContainer>
      </div>

      <div className="metric-card" style={{ gridColumn: 'span 2' }}>
        <h3>Cost by Model</h3>
        {costData?.by_model && Object.keys(costData.by_model).length > 0 ? (
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={Object.entries(costData.by_model).map(([model, cost]) => ({ model, cost }))}>
              <CartesianGrid strokeDasharray="3 3" stroke="#21262d" />
              <XAxis dataKey="model" stroke="#8b949e" />
              <YAxis stroke="#8b949e" />
              <Tooltip contentStyle={{ background: '#161b22', border: '1px solid #21262d' }} />
              <Bar dataKey="cost" fill="#238636" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <p style={{ color: '#8b949e', padding: 40, textAlign: 'center' }}>No cost data yet</p>
        )}
      </div>
    </div>
  )
}

function MetricCard({ title, value, sub }) {
  return (
    <div className="metric-card">
      <h3>{title}</h3>
      <div className="metric-value">{value}</div>
      <div className="metric-sub">{sub}</div>
    </div>
  )
}