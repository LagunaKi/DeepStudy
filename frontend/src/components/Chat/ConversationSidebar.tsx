import { ChatSessionSummary } from '../../types/api'
import './ConversationSidebar.css'

interface ConversationSidebarProps {
  sessions: ChatSessionSummary[]
  activeSessionId: string | null
  loading: boolean
  onCreate: () => void
  onSelect: (sessionId: string) => void
  onRename: (session: ChatSessionSummary) => void
  onDelete: (session: ChatSessionSummary) => void
}

const formatUpdatedAt = (value: string) => {
  const date = new Date(value)
  const today = new Date()
  if (date.toDateString() === today.toDateString()) {
    return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  return date.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
}

const ConversationSidebar = ({
  sessions,
  activeSessionId,
  loading,
  onCreate,
  onSelect,
  onRename,
  onDelete,
}: ConversationSidebarProps) => (
  <aside className="conversation-sidebar" aria-label="会话历史">
    <div className="conversation-brand">
      <div className="conversation-brand-mark">D</div>
      <div>
        <strong>DeepStudy</strong>
        <span>Agent 学习工作台</span>
      </div>
    </div>

    <button className="new-conversation-button" onClick={onCreate} disabled={loading}>
      <span aria-hidden="true">＋</span>
      新建学习会话
    </button>

    <div className="conversation-section-label">最近对话</div>
    <div className="conversation-list">
      {sessions.length === 0 && !loading && (
        <div className="conversation-empty">还没有历史会话</div>
      )}
      {sessions.map((session) => (
        <div
          key={session.id}
          className={`conversation-item ${activeSessionId === session.id ? 'active' : ''}`}
        >
          <button
            className="conversation-select"
            onClick={() => onSelect(session.id)}
            title={session.title}
          >
            <span className="conversation-title">{session.title}</span>
            <span className="conversation-meta">
              {session.message_count > 0 ? `${Math.ceil(session.message_count / 2)} 轮` : '空会话'}
              <span>·</span>
              {formatUpdatedAt(session.updated_at)}
            </span>
          </button>
          <div className="conversation-actions">
            <button onClick={() => onRename(session)} aria-label={`重命名 ${session.title}`}>✎</button>
            <button onClick={() => onDelete(session)} aria-label={`删除 ${session.title}`}>×</button>
          </div>
        </div>
      ))}
    </div>

    <div className="conversation-footer">
      <span className="status-dot" />
      Gemini 3 Flash · Free Tier
    </div>
  </aside>
)

export default ConversationSidebar
