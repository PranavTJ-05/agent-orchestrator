import { useEffect, useState } from 'react'
import { format } from 'date-fns'

export default function EventTimeline() {
  const [events, setEvents] = useState([])
  const [eventTypes, setEventTypes] = useState([])
  const [filter, setFilter] = useState('')

  useEffect(() => {
    fetch('/api/events/types').then(r => r.json()).then(d => setEventTypes(d.types || []))
    fetch('/api/events').then(r => r.json()).then(d => setEvents(d.events || []))
  }, [])

  const filteredEvents = filter 
    ? events.filter(e => e.type === filter) 
    : events

  return (
    <div className="event-timeline">
      <div style={{ marginBottom: 16, display: 'flex', gap: 12, alignItems: 'center' }}>
        <label>Filter by type:</label>
        <select 
          value={filter} 
          onChange={e => setFilter(e.target.value)}
          style={{ padding: '6px 12px', borderRadius: 6, background: '#161b22', color: '#e7e9ea', border: '1px solid #30363d' }}
        >
          <option value="">All Events</option>
          {eventTypes.map(t => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <span style={{ color: '#8b949e', marginLeft: 'auto' }}>{filteredEvents.length} events</span>
      </div>

      {filteredEvents.slice(0, 50).map((event, idx) => (
        <div key={idx} className={`event-item ${event.type.toLowerCase().replace(/_/g, '_')}`}>
          <span className="event-time">
            {event.timestamp ? format(new Date(event.timestamp), 'HH:mm:ss') : '--:--:--'}
          </span>
          <span className="event-type">{event.type}</span>
          <span className="event-details">
            {event.agent && `Agent: ${event.agent}`}
            {event.task_id && ` Task: ${event.task_id}`}
            {event.message && ` - ${event.message}`}
          </span>
        </div>
      ))}

      {filteredEvents.length === 0 && (
        <p style={{ color: '#8b949e', textAlign: 'center', padding: 40 }}>No events yet</p>
      )}
    </div>
  )
}