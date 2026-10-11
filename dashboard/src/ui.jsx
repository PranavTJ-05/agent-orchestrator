import { useEffect } from 'react'
import { Close } from './icons'

export function Switch({ checked, onChange, disabled, label }) {
  return <button role="switch" aria-checked={checked} aria-label={label} disabled={disabled} className="switch"
    onClick={(e) => { e.stopPropagation(); onChange(!checked) }} />
}

export function Segmented({ value, onChange, options }) {
  return (
    <div className="segmented" role="group">
      {options.map((o) => (
        <button key={o.value} aria-pressed={value === o.value} onClick={() => onChange(o.value)}>{o.label}</button>
      ))}
    </div>
  )
}

export function Sheet({ title, onClose, children, footer, wide }) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose?.()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="scrim" onMouseDown={(e) => e.target === e.currentTarget && onClose?.()}>
      <div className="sheet" role="dialog" aria-modal="true" aria-label={title} style={wide ? { width: 'min(680px,100%)' } : undefined}>
        <div className="sheet-head" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
          <h2 className="sheet-title">{title}</h2>
          {onClose && <button className="icon-btn" onClick={onClose} aria-label="Close"><Close /></button>}
        </div>
        <div className="sheet-body">{children}</div>
        {footer && <div className="sheet-foot">{footer}</div>}
      </div>
    </div>
  )
}

export const Spinner = () => <span className="spinner" role="status" aria-label="Loading" />
export const Dot = ({ status }) => <span className={`dot ${status}`} title={status} />

export function Empty({ title, children, action }) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      <p>{children}</p>
      {action && <div style={{ marginTop: 18 }}>{action}</div>}
    </div>
  )
}

export function PageHead({ title, subtitle, actions }) {
  return (
    <div className="page-head">
      <div>
        <h1 className="large-title">{title}</h1>
        {subtitle && <p className="subtitle">{subtitle}</p>}
      </div>
      {actions && <div style={{ display: 'flex', gap: 10 }}>{actions}</div>}
    </div>
  )
}

export function Toasts({ items }) {
  return <div className="toasts" aria-live="polite">{items.map((t) => <div key={t.id} className={`toast ${t.kind || ''}`}>{t.text}</div>)}</div>
}

export const clock = (ts) => new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
