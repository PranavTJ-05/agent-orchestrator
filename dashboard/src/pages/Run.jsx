import { useCallback, useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api } from '../api'
import { Arrow, Bolt, Sparkle } from '../icons'
import { Empty, PageHead, Spinner, clock } from '../ui'
import { useStudio } from '../studio/StudioContext'

const SUGGESTIONS = [
  'What is the current stock price of Tesla (TSLA)?',
  'Compare Tesla and BYD, then summarise the key risks',
  'Compute 15% compound interest on 1000 over 5 years',
]

const live = (e) => ({
  tools_picked: `Picked ${e.tools?.length ?? 0} tool${e.tools?.length === 1 ? '' : 's'} · ${e.method}`,
  tools_found: `Looking up more tools · ${e.need}`,
  tool_started: `Running ${e.server}.${e.tool}`,
  tool_finished: `${e.server}.${e.tool} ${e.ok ? 'done' : 'failed'} · ${e.ms} ms`,
  tool_denied: `Denied ${e.server}.${e.tool}`,
  approval_requested: `Waiting for your approval · ${e.server_id}.${e.tool}`,
}[e.type])

function Plan({ plan }) {
  if (!plan?.tasks?.length) return null
  return (
    <div className="group" style={{ marginTop: 14 }}>
      {plan.tasks.map((t, i) => (
        <div className="row" key={t.id || i} style={{ minHeight: 46, padding: '9px 18px' }}>
          <span className="badge blue" style={{ minWidth: 70, justifyContent: 'center' }}>{t.agent || 'auto'}</span>
          <div className="row-main" style={{ fontSize: 14 }}>{t.description}</div>
        </div>))}
    </div>
  )
}

export default function Run({ toast, go }) {
  const { status, subscribe } = useStudio()
  const [goal, setGoal] = useState('')
  const [running, setRunning] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [feed, setFeed] = useState([])
  const [result, setResult] = useState(null)
  const [history, setHistory] = useState([])
  const [openId, setOpenId] = useState(null)
  const area = useRef(null)

  const loadHistory = useCallback(() =>
    api('/sessions').then((d) => setHistory(Object.entries(d.sessions || {}).reverse().slice(0, 8))).catch(() => {}), [])
  useEffect(() => { loadHistory() }, [loadHistory])

  useEffect(() => subscribe((e) => {
    const text = live(e)
    if (text) setFeed((f) => [...f, { text, time: e.time, bad: e.type === 'tool_denied' || e.ok === false }].slice(-8))
  }), [subscribe])

  useEffect(() => {
    if (!running) return
    const t0 = Date.now()
    const t = setInterval(() => setElapsed(Math.round((Date.now() - t0) / 1000)), 500)
    return () => clearInterval(t)
  }, [running])

  useEffect(() => { // grow the textarea with its content
    const el = area.current
    if (el) { el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight, 260) + 'px' }
  }, [goal])

  const run = async () => {
    if (!goal.trim() || running) return
    setRunning(true); setResult(null); setFeed([]); setElapsed(0)
    try {
      const data = await api('/run', { method: 'POST', body: { goal: goal.trim() } })
      let plan = null
      try { plan = (await api(`/status/${data.session_id}`)).plan } catch { /* plan is optional */ }
      setResult({ ...data, goal: goal.trim(), plan })
      loadHistory()
    } catch (e) { toast(e.message, 'error') } finally { setRunning(false) }
  }

  return (
    <div className="page">
      <PageHead title="Run" subtitle="Describe what you want done. The orchestrator plans it, picks the right agents and tools, and reports back." />

      <div className="card composer">
        <textarea ref={area} className="textarea" placeholder="What would you like done?" value={goal} disabled={running}
          onChange={(e) => setGoal(e.target.value)} onKeyDown={(e) => (e.metaKey || e.ctrlKey) && e.key === 'Enter' && run()} />
        <div className="composer-foot">
          <button className="btn btn-plain btn-sm" onClick={() => go('studio')}>
            <Bolt />{status ? `${status.tools} MCP tool${status.tools === 1 ? '' : 's'} from ${status.connected} server${status.connected === 1 ? '' : 's'}` : 'MCP tools'}
          </button>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span className="caption">⌘↵</span>
            <button className="btn btn-primary btn-lg" disabled={!goal.trim() || running} onClick={run}>
              {running ? <><Spinner />Working</> : <>Run<Arrow /></>}
            </button>
          </div>
        </div>
      </div>

      {!running && !result && <div className="chips">{SUGGESTIONS.map((s) => <button key={s} className="chip" onClick={() => { setGoal(s); area.current?.focus() }}>{s}</button>)}</div>}

      {running && (
        <div className="card section" style={{ marginTop: 22 }}>
          <div className="row" style={{ borderBottom: feed.length ? '0.5px solid var(--sep)' : 0 }}>
            <Spinner /><div className="row-main"><div className="row-title">Planning and executing</div><div className="row-sub">Agents run in parallel waves; tool calls appear below</div></div>
            <span className="caption" style={{ fontVariantNumeric: 'tabular-nums' }}>{elapsed}s</span>
          </div>
          {feed.length > 0 && <div className="feed">{feed.map((f, i) => (
            <div className="feed-item" key={i}><Bolt width={14} height={14} style={{ color: f.bad ? 'var(--red)' : 'var(--accent)' }} />{f.text}<span className="t">{clock(f.time)}</span></div>))}</div>}
        </div>)}

      {result && (
        <div className="section">
          <div className="section-head"><span className="section-title">Result</span><span className="caption mono">{result.session_id}</span></div>
          <div className="card result"><div className="md"><ReactMarkdown remarkPlugins={[remarkGfm]}>{result.result}</ReactMarkdown></div></div>
          {result.plan?.tasks?.length > 0 && <>
            <div className="section-head" style={{ marginTop: 24 }}><span className="section-title">How it was done</span></div>
            <Plan plan={result.plan} />
          </>}
        </div>)}

      <div className="section">
        <div className="section-head"><span className="section-title">Recent</span></div>
        {history.length === 0
          ? <div className="card"><Empty title="Nothing yet">Your finished runs appear here.</Empty></div>
          : <div className="group">{history.map(([id, text]) => (
              <div className="row-wrap" key={id}>
                <div className="row clickable" onClick={() => setOpenId(openId === id ? null : id)}>
                  <Sparkle width={18} height={18} style={{ color: 'var(--accent)', flex: 'none' }} />
                  <div className="row-main"><div className="row-sub" style={{ color: 'var(--text)', fontSize: 14 }}>{String(text).replace(/[#*_`>|-]/g, '').slice(0, 120)}</div><div className="row-sub mono">{id}</div></div>
                </div>
                {openId === id && <div className="result" style={{ background: 'var(--surface-2)', borderTop: '0.5px solid var(--sep)' }}><div className="md"><ReactMarkdown remarkPlugins={[remarkGfm]}>{String(text)}</ReactMarkdown></div></div>}
              </div>))}</div>}
      </div>
    </div>
  )
}
