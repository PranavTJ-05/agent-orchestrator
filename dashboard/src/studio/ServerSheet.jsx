import { useState } from 'react'
import { api } from '../api'
import { Plus, Close, Warning } from '../icons'
import { Segmented, Sheet } from '../ui'

const APPROVAL = [
  { value: 'auto', label: 'Smart' },
  { value: 'ask', label: 'Always ask' },
  { value: 'allow', label: 'Allow all' },
  { value: 'block', label: 'Block' },
]
const APPROVAL_HELP = {
  auto: 'Read-only tools run on their own. Anything that writes, deletes, or isn’t marked read-only asks you first.',
  ask: 'Every tool call from this server waits for your approval.',
  allow: 'Tools run without asking. Only use this for servers you fully trust.',
  block: 'The server stays connected but its tools are hidden from the AI.',
}
const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 32)
const quote = (a) => (/\s/.test(a) ? JSON.stringify(a) : a)

function KeyValues({ label, items, setItems, keyPlaceholder, valuePlaceholder }) {
  const update = (i, patch) => setItems(items.map((it, j) => (j === i ? { ...it, ...patch } : it)))
  return (
    <div className="field">
      <label>{label}</label>
      {items.map((it, i) => (
        <div className="kv-row" key={i}>
          <input className="input mono" placeholder={keyPlaceholder} value={it.k} onChange={(e) => update(i, { k: e.target.value })} />
          <input className="input mono" placeholder={valuePlaceholder} value={it.v} type={it.v === '••••••••' ? 'text' : 'password'}
            autoComplete="off" onChange={(e) => update(i, { v: e.target.value })} onFocus={(e) => it.v === '••••••••' && e.target.select()} />
          <button className="icon-btn" aria-label="Remove" onClick={() => setItems(items.filter((_, j) => j !== i))}><Close /></button>
        </div>
      ))}
      <div><button className="btn btn-plain btn-sm" onClick={() => setItems([...items, { k: '', v: '' }])}><Plus />Add</button></div>
    </div>
  )
}

export default function ServerSheet({ server, onClose, onSaved, toast }) {
  const editing = !!server
  const spec = server?.spec
  const [name, setName] = useState(spec?.name || '')
  const [transport, setTransport] = useState(spec?.transport || 'stdio')
  const [cmd, setCmd] = useState(spec ? [spec.command, ...(spec.args || [])].filter(Boolean).map(quote).join(' ') : '')
  const [cwd, setCwd] = useState(spec?.cwd || '')
  const [url, setUrl] = useState(spec?.url || '')
  const [oauth, setOauth] = useState(spec?.oauth || false)
  const [env, setEnv] = useState(Object.entries(spec?.env || {}).map(([k, v]) => ({ k, v })))
  const [headers, setHeaders] = useState(Object.entries(spec?.headers || {}).map(([k, v]) => ({ k, v })))
  const [approval, setApproval] = useState(spec?.approval || 'auto')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const toMap = (rows) => Object.fromEntries(rows.filter((r) => r.k.trim()).map((r) => [r.k.trim(), r.v]))
  const valid = name.trim() && (transport === 'stdio' ? cmd.trim() : /^https?:\/\//.test(url.trim()))

  const save = async () => {
    setBusy(true); setError('')
    const body = {
      id: spec?.id || slug(name), name: name.trim(), transport,
      command: transport === 'stdio' ? cmd.trim() : null, args: [],
      env: transport === 'stdio' ? toMap(env) : {}, cwd: transport === 'stdio' && cwd.trim() ? cwd.trim() : null,
      url: transport === 'stdio' ? null : url.trim(), headers: transport === 'stdio' ? {} : toMap(headers),
      oauth: transport === 'stdio' ? false : oauth, enabled: spec?.enabled ?? true, approval,
    }
    try {
      // The backend splits "npx -y pkg" into command + args; for edits keep what the user typed.
      const saved = editing
        ? await api(`/studio/servers/${body.id}`, { method: 'PUT', body })
        : await api('/studio/servers', { method: 'POST', body })
      toast(editing ? 'Saved' : `${body.name} added`)
      onSaved?.(saved); onClose()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  return (
    <Sheet title={editing ? `Edit ${spec.name}` : 'Add MCP Server'} onClose={onClose} footer={<>
      <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
      <button className="btn btn-primary" disabled={!valid || busy} onClick={save}>{editing ? 'Save' : 'Add Server'}</button>
    </>}>
      <div className="field">
        <label>Name</label>
        <input className="input" autoFocus placeholder="e.g. Filesystem" value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <div className="field">
        <label>Connection</label>
        <Segmented value={transport} onChange={setTransport} options={[
          { value: 'stdio', label: 'Local command' }, { value: 'http', label: 'Remote (HTTP)' }, { value: 'sse', label: 'Remote (SSE)' }]} />
      </div>

      {transport === 'stdio' ? (<>
        <div className="field">
          <label>Command</label>
          <input className="input mono" placeholder="npx -y @modelcontextprotocol/server-filesystem ~/Documents" value={cmd} onChange={(e) => setCmd(e.target.value)} />
          <span className="hint">Paste the same command you would put in another MCP client’s config.</span>
        </div>
        <div className="field">
          <label>Working directory (optional)</label>
          <input className="input mono" placeholder="Leave empty to use the project folder" value={cwd} onChange={(e) => setCwd(e.target.value)} />
        </div>
        <KeyValues label="Environment variables" items={env} setItems={setEnv} keyPlaceholder="GITHUB_TOKEN" valuePlaceholder="value" />
        <div className="notice"><Warning /><span>Local servers run as programs on your computer with your permissions. Only add commands you trust.</span></div>
      </>) : (<>
        <div className="field">
          <label>Server URL</label>
          <input className="input mono" placeholder="https://mcp.example.com/mcp" value={url} onChange={(e) => setUrl(e.target.value)} />
        </div>
        <KeyValues label="Headers" items={headers} setItems={setHeaders} keyPlaceholder="Authorization" valuePlaceholder="Bearer …" />
        <div className="row" style={{ padding: 0, minHeight: 0 }}>
          <div className="row-main"><div className="row-title">Sign in with OAuth</div><div className="row-sub">For servers that ask you to log in through your browser</div></div>
          <button role="switch" aria-checked={oauth} className="switch" onClick={() => setOauth(!oauth)} />
        </div>
      </>)}

      <div className="field">
        <label>Approvals</label>
        <Segmented value={approval} onChange={setApproval} options={APPROVAL} />
        <span className="hint">{APPROVAL_HELP[approval]}</span>
      </div>
      {error && <div className="error-note" style={{ margin: 0 }}>{error}</div>}
    </Sheet>
  )
}
