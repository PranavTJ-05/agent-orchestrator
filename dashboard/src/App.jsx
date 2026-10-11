import { useCallback, useEffect, useState } from 'react'
import { Chart, People, Plug, Pulse, Sparkle } from './icons'
import { Toasts } from './ui'
import ApprovalSheet from './studio/ApprovalSheet'
import { StudioProvider, useStudio } from './studio/StudioContext'
import Activity from './pages/Activity'
import Agents from './pages/Agents'
import Insights from './pages/Insights'
import Run from './pages/Run'
import Studio from './pages/Studio'

const PAGES = [
  { id: 'run', label: 'Run', icon: Sparkle },
  { id: 'studio', label: 'Studio', icon: Plug },
  { id: 'activity', label: 'Activity', icon: Pulse },
  { id: 'insights', label: 'Insights', icon: Chart },
  { id: 'agents', label: 'Agents', icon: People },
]
const fromHash = () => (PAGES.find((p) => `#/${p.id}` === window.location.hash) || PAGES[0]).id

function Shell({ toast }) {
  const [page, setPage] = useState(fromHash())
  const { status, approvals } = useStudio()
  useEffect(() => { const on = () => setPage(fromHash()); window.addEventListener('hashchange', on); return () => window.removeEventListener('hashchange', on) }, [])
  const go = useCallback((id) => { window.location.hash = `/${id}` }, [])
  const View = { run: Run, studio: Studio, activity: Activity, insights: Insights, agents: Agents }[page]
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand"><div className="brand-mark"><Sparkle width={16} height={16} /></div>Orchestrator</div>
        <div className="nav-label">Workspace</div>
        {PAGES.map(({ id, label, icon: Icon }) => (
          <a key={id} href={`#/${id}`} className={`nav-item ${page === id ? 'active' : ''}`}><Icon />{label}
            {id === 'studio' && approvals.length > 0 && <span className="count">{approvals.length}</span>}</a>))}
        <div className="sidebar-foot">{status ? `${status.connected}/${status.servers} servers · ${status.tools} tools` : 'Connecting…'}</div>
      </aside>
      <main className="main"><View toast={toast} go={go} /></main>
      <ApprovalSheet />
    </div>
  )
}

export default function App() {
  const [toasts, setToasts] = useState([])
  const toast = useCallback((text, kind) => {
    const id = Math.random()
    setToasts((t) => [...t, { id, text, kind }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), kind === 'error' ? 6000 : 2600)
  }, [])
  return (
    <StudioProvider toast={toast}>
      <Shell toast={toast} />
      <Toasts items={toasts} />
    </StudioProvider>
  )
}
