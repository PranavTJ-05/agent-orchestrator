import { useEffect, useState, useCallback } from 'react'
import ReactFlow, { Background, Controls, MiniMap, useNodesState, useEdgesState } from 'reactflow'
import 'reactflow/dist/style.css'

const API_BASE = '/api'

const nodeStyles = {
  background: '#161b22',
  border: '1px solid #21262d',
  borderRadius: '8px',
  padding: '10px',
  color: '#e7e9ea',
  fontSize: '12px',
  width: 150,
}

const getNodeColor = (status) => {
  switch (status) {
    case 'completed': return '#238636'
    case 'running': return '#58a6ff'
    case 'pending': return '#8b949e'
    case 'failed': return '#f85149'
    default: return '#21262d'
  }
}

export default function DAGGraph({ sessionId }) {
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [dagData, setDagData] = useState(null)
  const [loading, setLoading] = useState(false)

  const fetchDAG = useCallback(async () => {
    const generateDag = async () => {
      const res = await fetch('/api/dag', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ goal: 'Analyze AI trends' })
      })
      if (!res.ok) throw new Error('Failed to fetch DAG')
      return await res.json()
    }

    if (!sessionId) {
      try {
        const data = await generateDag()
        setDagData(data)
      } catch (err) {
        console.error('DAG fetch error:', err)
        setDagData({ plan: { tasks: [], edges: [] } })
      }
    } else {
      try {
        const res = await fetch(`/api/dag/${sessionId}`)
        if (res.ok) {
          const data = await res.json()
          setDagData(data)
        } else {
          // Session not found - generate new DAG
          console.log('Session not found, generating new DAG...')
          const data = await generateDag()
          setDagData(data)
        }
      } catch (err) {
        console.error('Session DAG fetch error:', err)
        const data = await generateDag()
        setDagData(data)
      }
    }
  }, [sessionId])

  useEffect(() => {
    setLoading(true)
    fetchDAG().finally(() => setLoading(false))
  }, [fetchDAG])

  useEffect(() => {
    if (!dagData?.plan?.tasks) return

    const taskNodes = dagData.plan.tasks.map((task, idx) => ({
      id: task.id || `task_${idx}`,
      position: { 
        x: 250 * (idx % 3), 
        y: Math.floor(idx / 3) * 150 
      },
      data: { label: task.description || task.id, status: task.status },
      style: {
        ...nodeStyles,
        borderColor: getNodeColor(task.status),
      },
    }))

    const taskEdges = []
    dagData.plan.tasks.forEach((task, idx) => {
      if (task.dependencies) {
        task.dependencies.forEach(depId => {
          taskEdges.push({
            id: `${depId}-${task.id}`,
            source: depId,
            target: task.id || `task_${idx}`,
            animated: task.status === 'running',
            style: { stroke: '#30363d' },
          })
        })
      }
    })

    setNodes(taskNodes)
    setEdges(taskEdges)
  }, [dagData, setNodes, setEdges])

  if (loading) {
    return <div className="dag-container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>Loading DAG...</div>
  }

  if (!sessionId && !dagData) {
    return (
      <div className="dag-container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 16 }}>
        <p>Enter a session ID or click "Run Goal" to generate a DAG</p>
      </div>
    )
  }

  return (
    <div className="dag-container" style={{ height: '100%', minHeight: 500 }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        fitView
      >
        <Background color="#21262d" gap={20} />
        <Controls />
        <MiniMap nodeColor={getNodeColor} />
      </ReactFlow>
    </div>
  )
}