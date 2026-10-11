import { useState, useEffect } from 'react'
import DAGGraph from './components/DAGGraph'
import EventTimeline from './components/EventTimeline'
import MetricsDashboard from './components/MetricsDashboard'
import './App.css'

const API_BASE = '/api'

function App() {
  const [activeTab, setActiveTab] = useState('dag')
  const [sessionId, setSessionId] = useState('')
  const [sessions, setSessions] = useState([])

  useEffect(() => {
    fetch('/api/sessions')
      .then(r => r.ok ? r.json() : Promise.reject('Failed'))
      .then(d => setSessions(Object.keys(d.sessions || {})))
      .catch(() => setSessions([]))
  }, [])

  const runGoal = async () => {
    const actualSessionId = sessionId || `session_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
    try {
      const res = await fetch('/api/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ goal: 'Research and analyze AI trends', session_id: actualSessionId })
      })
      if (!res.ok) throw new Error('Execution failed')
      const data = await res.json()
      console.log('Execution started:', data)
      setSessionId(actualSessionId)
      setSessions([...sessions, actualSessionId])
    } catch (err) {
      console.error('Run error:', err)
      alert('Failed to run goal: ' + err.message)
    }
  }

  return (
    <div className="app">
      <header className="header">
        <h1>🤖 AI Agent Orchestrator</h1>
        <div className="controls">
          <input 
            type="text" 
            placeholder="Session ID (optional)" 
            value={sessionId}
            onChange={e => setSessionId(e.target.value)}
          />
          <button onClick={runGoal}>Run Goal</button>
        </div>
      </header>

      <nav className="tabs">
        <button className={activeTab === 'dag' ? 'active' : ''} onClick={() => setActiveTab('dag')}>DAG Graph</button>
        <button className={activeTab === 'events' ? 'active' : ''} onClick={() => setActiveTab('events')}>Events</button>
        <button className={activeTab === 'metrics' ? 'active' : ''} onClick={() => setActiveTab('metrics')}>Metrics</button>
        <button className={activeTab === 'agents' ? 'active' : ''} onClick={() => setActiveTab('agents')}>Agents</button>
      </nav>

      <main className="content">
        {activeTab === 'dag' && <DAGGraph sessionId={sessionId} />}
        {activeTab === 'events' && <EventTimeline />}
        {activeTab === 'metrics' && <MetricsDashboard />}
        {activeTab === 'agents' && <AgentsView />}
      </main>
    </div>
  )
}

function AgentsView() {
  const [agents, setAgents] = useState([])
  const [capabilities, setCapabilities] = useState([])

  useEffect(() => {
    fetch('/api/marketplace/agents').then(r => r.json()).then(d => setAgents(d))
    fetch('/api/marketplace/capabilities').then(r => r.json()).then(d => setCapabilities(d))
  }, [])

  return (
    <div className="agents-view">
      <h2>Agent Marketplace</h2>
      <div className="agent-grid">
        {agents.map(agent => (
          <div key={agent.name} className="agent-card">
            <h3>{agent.name}</h3>
            <p>{agent.description}</p>
            <div className="tags">
              {(agent.capabilities || []).map((c, i) => (
                <span key={i} className="tag">
                  {typeof c === 'string' ? c : c.capability}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default App