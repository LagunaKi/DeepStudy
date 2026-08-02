import { useMemo, useState } from 'react'

import { AgentTraceEvent } from '../../types/api'
import './AgentTrace.css'

interface AgentTraceProps {
  events: AgentTraceEvent[]
  active?: boolean
}

const nodeIcon: Record<string, string> = {
  router: 'R',
  planner: 'P',
  agent_model: 'A',
  tool_executor: 'T',
  verifier: 'V',
  memory_writer: 'M',
}

const AgentTrace = ({ events, active = false }: AgentTraceProps) => {
  const [expanded, setExpanded] = useState(true)
  const visibleEvents = useMemo(() => {
    // running/completed 常成对出现：保留每个节点+标题的最后状态，工具调用则逐个保留。
    const compacted: AgentTraceEvent[] = []
    events.forEach((event) => {
      const previousIndex = compacted.findIndex((item) => (
        item.node === event.node
        && item.title === event.title
        && event.node !== 'tool_executor'
      ))
      if (previousIndex >= 0) compacted[previousIndex] = event
      else compacted.push(event)
    })
    return compacted
  }, [events])

  if (visibleEvents.length === 0) return null
  const completedCount = visibleEvents.filter((event) => event.status === 'completed').length

  return (
    <section className="agent-trace" aria-label="Agent 执行轨迹">
      <button
        type="button"
        className="agent-trace-header"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
      >
        <span className={`agent-trace-pulse ${active ? 'is-active' : ''}`} />
        <span>Agent Trace</span>
        <small>{active ? '执行中' : `${completedCount}/${visibleEvents.length} 已完成`}</small>
        <span className="agent-trace-chevron">{expanded ? '−' : '+'}</span>
      </button>
      {expanded && (
        <ol className="agent-trace-list">
          {visibleEvents.map((event, index) => (
            <li key={`${event.node}-${event.title}-${index}`} className={`is-${event.status}`}>
              <span className="agent-trace-node">{nodeIcon[event.node] || '•'}</span>
              <div>
                <strong>{event.title}</strong>
                <p>{event.summary}</p>
              </div>
              <span className="agent-trace-status">
                {event.status === 'running' ? '进行中' : event.status === 'failed' ? '已降级' : '完成'}
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}

export default AgentTrace
