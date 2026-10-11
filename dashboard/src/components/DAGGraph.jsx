import { useEffect, useMemo } from 'react'
import ReactFlow, { Background, Controls, MarkerType, useEdgesState, useNodesState } from 'reactflow'
import 'reactflow/dist/style.css'

const AGENT_COLOR = { research: '#0a84ff', finance: '#30b0c7', coding: '#34c759', code: '#34c759', mcp: '#bf5af2', critic: '#ff9f0a', reviewer: '#ff375f', synthesizer: '#5e5ce6' }

/** Layered layout: a task sits one column right of its deepest dependency. */
function layout(tasks) {
  const byId = Object.fromEntries(tasks.map((t) => [t.id, t]))
  const depth = {}
  const level = (t, seen = new Set()) => {
    if (depth[t.id] !== undefined) return depth[t.id]
    if (seen.has(t.id)) return 0
    seen.add(t.id)
    return (depth[t.id] = (t.deps || []).reduce((m, d) => (byId[d] ? Math.max(m, level(byId[d], seen) + 1) : m), 0))
  }
  const rows = {}
  return tasks.map((t) => {
    const col = level(t)
    const row = (rows[col] = (rows[col] ?? -1) + 1)
    return { t, x: col * 300, y: row * 110 }
  })
}

export default function DAGGraph({ tasks }) {
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const placed = useMemo(() => layout(tasks || []), [tasks])
  useEffect(() => {
    setNodes(placed.map(({ t, x, y }) => ({
      id: t.id, position: { x, y }, draggable: true, sourcePosition: 'right', targetPosition: 'left',
      data: { label: (
        <div style={{ textAlign: 'left' }}>
          <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: '.05em', textTransform: 'uppercase', color: AGENT_COLOR[t.agent] || 'var(--text-3)' }}>{t.agent || 'auto'}</div>
          <div style={{ fontSize: 13, marginTop: 3, lineHeight: 1.35 }}>{t.description}</div>
        </div>) },
      style: { width: 240, padding: '12px 14px', borderRadius: 14, border: '0.5px solid var(--sep)', background: 'var(--surface)', color: 'var(--text)', boxShadow: 'var(--shadow-card)' },
    })))
    setEdges(placed.flatMap(({ t }) => (t.deps || []).map((d) => ({
      id: `${d}-${t.id}`, source: d, target: t.id, markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 }, style: { strokeWidth: 1.5 },
    }))))
  }, [placed, setNodes, setEdges])
  return (
    <div className="flow">
      <ReactFlow nodes={nodes} edges={edges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} fitView fitViewOptions={{ padding: 0.25 }} proOptions={{ hideAttribution: true }}>
        <Background gap={22} color="var(--sep)" />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  )
}
