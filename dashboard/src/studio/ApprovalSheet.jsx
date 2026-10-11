import { useEffect, useState } from 'react'
import { Shield, Warning } from '../icons'
import { Sheet } from '../ui'
import { useStudio } from './StudioContext'

export default function ApprovalSheet() {
  const { approvals, decide } = useStudio()
  const [now, setNow] = useState(Date.now() / 1000)
  useEffect(() => { const t = setInterval(() => setNow(Date.now() / 1000), 1000); return () => clearInterval(t) }, [])
  const item = approvals[0]
  if (!item) return null
  const left = Math.max(0, Math.round(120 - (now - item.created_at)))
  return (
    <Sheet title="Allow this action?" footer={<>
      <button className="btn btn-secondary" onClick={() => decide(item.id, false)}>Don’t Allow</button>
      <button className="btn btn-primary" onClick={() => decide(item.id, true)} autoFocus>Allow</button>
    </>}>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
        <div className="brand-mark" style={{ background: item.destructive ? 'linear-gradient(160deg,#ff6a5f,#e5352b)' : undefined }}><Shield width={16} height={16} /></div>
        <div>
          <div className="row-title"><span className="mono">{item.server_id}.{item.tool}</span></div>
          <div className="caption">The AI wants to run this tool{approvals.length > 1 ? ` · ${approvals.length - 1} more waiting` : ''}</div>
        </div>
      </div>
      {item.destructive && <div className="notice"><Warning /><span>This tool is marked <b>destructive</b> by its server. It may change or delete data.</span></div>}
      <div>
        <div className="label" style={{ marginBottom: 6 }}>Arguments</div>
        <div className="args">{JSON.stringify(item.arguments, null, 2)}</div>
      </div>
      <div className="hint">Denied automatically in {left}s if you don’t respond.</div>
    </Sheet>
  )
}
