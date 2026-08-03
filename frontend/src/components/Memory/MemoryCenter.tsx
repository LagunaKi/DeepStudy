import { useCallback, useEffect, useState } from 'react'
import { memoryAPI } from '../../services/api'
import { MemoryRecord } from '../../types/api'
import './MemoryCenter.css'

interface Props {
  open: boolean
  onClose: () => void
}

const labels: Record<string, string> = {
  explicit: '明确记住',
  goal: '学习目标',
  preference: '交互偏好',
  background: '学习基础',
  user_note: '手动记忆',
  learning_turn: '学习情景',
}

const MemoryCenter = ({ open, onClose }: Props) => {
  const [items, setItems] = useState<MemoryRecord[]>([])
  const [tab, setTab] = useState<'semantic' | 'episodic'>('semantic')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [draft, setDraft] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingContent, setEditingContent] = useState('')

  const reload = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      setItems(await memoryAPI.list())
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '记忆加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (open) void reload()
  }, [open, reload])

  if (!open) return null
  const visible = items.filter((item) => item.scope === tab)

  return (
    <div className="memory-overlay" onClick={onClose}>
      <section className="memory-panel" onClick={(event) => event.stopPropagation()}>
        <header className="memory-header">
          <div>
            <h2>记忆中心</h2>
            <p>你可以确认、修正或永久遗忘 Agent 保存的长期记忆。</p>
          </div>
          <button className="memory-close" onClick={onClose}>×</button>
        </header>

        <div className="memory-privacy">
          短期聊天与运行 checkpoint 不在这里展示；下方只包含会跨会话检索的长期记忆。
        </div>

        <nav className="memory-tabs">
          <button className={tab === 'semantic' ? 'active' : ''} onClick={() => setTab('semantic')}>
            语义记忆
          </button>
          <button className={tab === 'episodic' ? 'active' : ''} onClick={() => setTab('episodic')}>
            学习情景
          </button>
        </nav>

        {tab === 'semantic' && (
          <form
            className="memory-create"
            onSubmit={async (event) => {
              event.preventDefault()
              if (!draft.trim()) return
              try {
                const memory = await memoryAPI.create(draft.trim())
                setItems((previous) => [memory, ...previous.filter((item) => item.id !== memory.id)])
                setDraft('')
              } catch (reason) {
                setError(reason instanceof Error ? reason.message : '添加失败')
              }
            }}
          >
            <input value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="例如：我偏好先看直觉例子，再看公式" />
            <button disabled={!draft.trim()}>添加并确认</button>
          </form>
        )}

        {error && <div className="memory-error">{error}</div>}
        <div className="memory-list">
          {loading && <div className="memory-empty">正在加载…</div>}
          {!loading && visible.length === 0 && <div className="memory-empty">暂无这类长期记忆</div>}
          {!loading && visible.map((item) => (
            <article className="memory-card" key={item.id}>
              <div className="memory-card-top">
                <span className={`memory-kind ${item.scope}`}>{labels[item.kind] || item.kind}</span>
                <span className="memory-meta">
                  置信度 {Math.round(item.confidence * 100)}% · 使用 {item.access_count} 次
                </span>
              </div>
              {editingId === item.id ? (
                <textarea value={editingContent} onChange={(event) => setEditingContent(event.target.value)} />
              ) : (
                <p>{item.content}</p>
              )}
              <div className="memory-actions">
                {item.scope === 'semantic' && !item.user_confirmed && (
                  <button onClick={async () => {
                    const updated = await memoryAPI.update(item.id, { user_confirmed: true })
                    setItems((previous) => previous.map((current) => current.id === item.id ? updated : current))
                  }}>确认正确</button>
                )}
                {editingId === item.id ? (
                  <>
                    <button onClick={async () => {
                      const updated = await memoryAPI.update(item.id, { content: editingContent, user_confirmed: true })
                      setItems((previous) => previous.map((current) => current.id === item.id ? updated : current))
                      setEditingId(null)
                    }}>保存</button>
                    <button onClick={() => setEditingId(null)}>取消</button>
                  </>
                ) : item.scope === 'semantic' && (
                  <button onClick={() => { setEditingId(item.id); setEditingContent(item.content) }}>编辑</button>
                )}
                <button className="danger" onClick={async () => {
                  if (!window.confirm('永久遗忘这条记忆？删除后无法恢复。')) return
                  await memoryAPI.remove(item.id)
                  setItems((previous) => previous.filter((current) => current.id !== item.id))
                }}>永久遗忘</button>
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  )
}

export default MemoryCenter
