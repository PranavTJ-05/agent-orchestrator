import { useMemo, useState } from 'react'
import { api } from '../api'
import { Bolt, Chevron, Edit, Plug, Plus, Refresh, Search, Trash } from '../icons'
import { Dot, Empty, PageHead, Spinner, Switch, clock } from '../ui'
import ServerSheet from '../studio/ServerSheet'
import { useStudio } from '../studio/StudioContext'

const STATUS_LABEL = { connected: 'Connected', connecting: 'Connecting…', error: 'Can’t connect', disabled: 'Off', needs_auth: 'Sign-in needed' }
const where = (spec) => (spec.transport === 'stdio' ? [spec.command, ...(spec.args || [])].join(' ') : spec.url)

function ToolBadges({ tool }) {
  if (tool.read_only) return <span className="badge green">Read-only</span>
  return <>
    {tool.destructive && <span className="badge red">Destructive</span>}
    {tool.needs_approval && <span className="badge orange">Asks first</span>}
  </>
}

function ServerRow({ server, open, onToggleOpen, onEdit, toast, tools }) {
  const { spec } = server
  const [busy, setBusy] = useState(false)
  const act = async (fn, ok) => {
    setBusy(true)
    try { await fn(); ok && toast(ok) } catch (e) { toast(e.message, 'error') } finally { setBusy(false) }
  }
  const mine = tools.filter((t) => t.server_id === spec.id)
  return (
    <div className="row-wrap">
      <div className="row clickable" onClick={onToggleOpen}>
        <Chevron width={16} height={16} style={{ transform: open ? 'rotate(90deg)' : 'none', transition: 'transform .2s', color: 'var(--text-3)' }} />
        <Dot status={server.status} />
        <div className="row-main">
          <div className="row-title">{spec.name}
            <span className="badge">{spec.transport === 'stdio' ? 'Local' : spec.transport.toUpperCase()}</span>
            {spec.approval !== 'auto' && <span className={`badge ${spec.approval === 'block' ? 'red' : spec.approval === 'allow' ? 'orange' : 'blue'}`}>{spec.approval === 'ask' ? 'Always ask' : spec.approval === 'allow' ? 'Allow all' : 'Blocked'}</span>}
          </div>
          <div className="row-sub mono">{STATUS_LABEL[server.status]}{server.status === 'connected' ? ` · ${server.tool_count} tool${server.tool_count === 1 ? '' : 's'}` : ''} · {where(spec)}</div>
        </div>
        {server.status === 'needs_auth' && server.auth_url &&
          <button className="btn btn-primary btn-sm" onClick={(e) => { e.stopPropagation(); window.open(server.auth_url, '_blank', 'noopener,width=520,height=700') }}>Sign in</button>}
        <Switch label={`Enable ${spec.name}`} checked={spec.enabled} disabled={busy}
          onChange={(v) => act(() => api(`/studio/servers/${spec.id}/enabled`, { method: 'POST', body: { enabled: v } }))} />
      </div>
      {open && <>
        {server.error && <div className="error-note" style={{ marginTop: 0, paddingTop: 10 }}>{server.error}</div>}
        <div className="tool-list">
          {mine.length === 0
            ? <div className="caption" style={{ padding: '10px 0' }}>{server.status === 'connected' ? 'This server has no tools.' : 'Tools appear here once the server is connected.'}</div>
            : mine.map((t) => (
              <div className="tool-row" key={t.qualified}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="tool-name">{t.name}</div>
                  {t.description && <div className="tool-desc">{t.description.length > 180 ? t.description.slice(0, 180) + '…' : t.description}</div>}
                </div>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', justifyContent: 'flex-end' }}><ToolBadges tool={t} /></div>
              </div>))}
        </div>
        <div className="row-actions">
          <button className="btn btn-secondary btn-sm" onClick={onEdit}><Edit />Edit</button>
          <button className="btn btn-secondary btn-sm" disabled={busy} onClick={() => act(() => api(`/studio/servers/${spec.id}/reconnect`, { method: 'POST' }), 'Reconnecting')}><Refresh />Reconnect</button>
          <button className="btn btn-danger btn-sm" disabled={busy} style={{ marginLeft: 'auto' }}
            onClick={() => window.confirm(`Remove ${spec.name}? Its saved sign-in is deleted too.`) && act(() => api(`/studio/servers/${spec.id}`, { method: 'DELETE' }), `${spec.name} removed`)}><Trash />Remove</button>
        </div>
      </>}
    </div>
  )
}

function Picker({ toast }) {
  const { tools } = useStudio()
  const [task, setTask] = useState('')
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const go = async () => {
    if (!task.trim()) return
    setBusy(true)
    try { setResult(await api('/studio/pick', { method: 'POST', body: { task } })) }
    catch (e) { toast(e.message, 'error') } finally { setBusy(false) }
  }
  const label = { jev: 'Jev model', 'jev-two-stage': 'Jev model · two steps', keyword: 'Keyword match', all: 'All tools (few enough to skip ranking)' }
  return (
    <div className="card card-pad">
      <div style={{ display: 'flex', gap: 10 }}>
        <input className="input" placeholder="Describe a task, e.g. “save a note that the deploy is done”" value={task}
          onChange={(e) => setTask(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && go()} />
        <button className="btn btn-primary" disabled={busy || !task.trim() || tools.length === 0} onClick={go}>{busy ? <Spinner /> : <Search />}Rank</button>
      </div>
      {tools.length === 0 && <p className="hint" style={{ marginTop: 10 }}>Connect a server to try the picker.</p>}
      {result && <div style={{ marginTop: 18 }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12 }}>
          <span className="badge blue">{label[result.method] || result.method}</span>
          <span className="caption">{result.ms} ms</span>
          {result.low_confidence && <span className="badge orange">Low confidence · the AI will choose among these</span>}
        </div>
        {result.tools.map((t) => (
          <div key={t.qualified} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '6px 0' }}>
            <span className="tool-name" style={{ width: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.server_id}.{t.name}</span>
            <div className="bar-track"><div className="bar-fill" style={{ width: `${Math.round(t.probability * 100)}%` }} /></div>
            <span className="caption" style={{ width: 44, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{Math.round(t.probability * 100)}%</span>
          </div>))}
      </div>}
    </div>
  )
}

const describe = (e) => ({
  tools_picked: { icon: 'pick', text: `Picked ${e.tools?.length ?? 0} tool${e.tools?.length === 1 ? '' : 's'} (${e.method}, ${e.ms} ms)`, sub: (e.tools || []).join(', ') },
  tools_found: { icon: 'pick', text: `Looked up more tools: ${e.need}`, sub: (e.added || []).join(', ') },
  tool_started: { icon: 'run', text: `Running ${e.server}.${e.tool}`, sub: JSON.stringify(e.arguments) },
  tool_finished: { icon: e.ok ? 'ok' : 'bad', text: `${e.server}.${e.tool} ${e.ok ? 'finished' : 'failed'} in ${e.ms} ms`, sub: e.preview },
  tool_denied: { icon: 'bad', text: `Denied ${e.server}.${e.tool}`, sub: '' },
}[e.type])

function Activity() {
  const { events } = useStudio()
  const rows = events.map((e) => ({ e, d: describe(e) })).filter((r) => r.d).slice(0, 12)
  if (!rows.length) return <div className="card"><Empty title="No tool activity yet">Tool calls and the tools the AI picked show up here as they happen.</Empty></div>
  const color = { ok: 'var(--green)', bad: 'var(--red)', run: 'var(--accent)', pick: 'var(--text-3)' }
  return <div className="group">{rows.map(({ e, d }, i) => (
    <div className="row" key={i} style={{ minHeight: 48, padding: '10px 18px' }}>
      <Bolt width={16} height={16} style={{ color: color[d.icon], flex: 'none' }} />
      <div className="row-main"><div style={{ fontSize: 14, fontWeight: 500 }}>{d.text}</div>{d.sub && <div className="row-sub mono">{d.sub}</div>}</div>
      <span className="caption" style={{ fontVariantNumeric: 'tabular-nums' }}>{clock(e.time)}</span>
    </div>))}</div>
}

export default function Studio({ toast }) {
  const { servers, tools, status, online } = useStudio()
  const [sheet, setSheet] = useState(null) // null | 'new' | server
  const [open, setOpen] = useState(null)
  const connected = servers.filter((s) => s.status === 'connected').length
  const jev = status?.jev
  const ordered = useMemo(() => servers, [servers])

  return (
    <div className="page">
      <PageHead title="Studio" subtitle="Connect MCP servers and the AI picks the right one for each task, then calls its tools safely."
        actions={<button className="btn btn-primary" onClick={() => setSheet('new')}><Plus />Add Server</button>} />
      {!online && <div className="notice" style={{ marginBottom: 20 }}><span>Can’t reach the orchestrator API. Start it with <code>orchestrator serve --port 8003</code>.</span></div>}

      <div className="stats">
        <div className="card stat"><div className="stat-label">Servers</div><div className="stat-value">{connected}<span className="muted" style={{ fontSize: 20 }}> / {servers.length}</span></div><div className="stat-sub">connected</div></div>
        <div className="card stat"><div className="stat-label">Tools available</div><div className="stat-value">{tools.length}</div><div className="stat-sub">across all servers</div></div>
        <div className="card stat"><div className="stat-label">Tool picker</div>
          <div className="stat-value" style={{ fontSize: 22, paddingTop: 6 }}>{jev ? (jev.available ? 'Jev on-device' : 'Keyword fallback') : '—'}</div>
          <div className="stat-sub">{jev?.available ? 'Calibrated, runs on CPU' : jev?.error || 'Jev model not found, using keyword matching'}</div></div>
      </div>

      <div className="section">
        <div className="section-head"><span className="section-title">Servers</span></div>
        {servers.length === 0
          ? <div className="card"><Empty title="No servers yet" action={<button className="btn btn-primary" onClick={() => setSheet('new')}><Plug />Add your first server</button>}>
              Add a local command like <code>npx -y @modelcontextprotocol/server-filesystem</code> or a remote URL.</Empty></div>
          : <div className="group">{ordered.map((s) => (
              <ServerRow key={s.spec.id} server={s} tools={tools} toast={toast} open={open === s.spec.id}
                onToggleOpen={() => setOpen(open === s.spec.id ? null : s.spec.id)} onEdit={() => setSheet(s)} />))}</div>}
      </div>

      <div className="section">
        <div className="section-head"><span className="section-title">Tool picker</span><span className="caption">See which tools the AI would be given for a task</span></div>
        <Picker toast={toast} />
      </div>

      <div className="section">
        <div className="section-head"><span className="section-title">Activity</span></div>
        <Activity />
      </div>

      {sheet && <ServerSheet server={sheet === 'new' ? null : sheet} toast={toast} onClose={() => setSheet(null)} />}
    </div>
  )
}
