import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { authAPI, chatAPI, mindMapAPI } from '../../services/api'
import { AgentResponse, MindMapGraph } from '../../types/api'
import TextFragment from '../Markdown/TextFragment'
import KnowledgeGraph from '../MindMap/KnowledgeGraph'

/**
 * 聊天界面主组件
 * 包含对话展示、输入框、思维导图侧边栏
 */
const ChatInterface = () => {
  const navigate = useNavigate()
  
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  
  const [messages, setMessages] = useState<AgentResponse[]>([])
  const [userMessages, setUserMessages] = useState<string[]>([])
  const [input, setInput] = useState<string>('')
  const [loading, setLoading] = useState<boolean>(false)
  const [hasFirstChunk, setHasFirstChunk] = useState<boolean>(false)
  const [error, setError] = useState<string>('')
  const [mindMapData, setMindMapData] = useState<MindMapGraph>({ nodes: [], edges: [] })
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(true)
  const [sidebarWidth, setSidebarWidth] = useState<number>(400) // 侧边栏宽度
  const [isResizing, setIsResizing] = useState<boolean>(false) // 是否正在调整大小
  const [sessionId] = useState<string>(() => `session_${Date.now()}`)
  const [questionModalOpen, setQuestionModalOpen] = useState(false)
  const [selectedFragmentId, setSelectedFragmentId] = useState<string>('')
  const [selectedText, setSelectedText] = useState<string>('')
  const [questionInput, setQuestionInput] = useState<string>('')

  // ==========================================
  // 👇👇👇 稳健滚动逻辑 (使用 requestAnimationFrame) 👇👇👇
  // ==========================================

  const scrollToBottom = (behavior: 'auto' | 'smooth' = 'smooth') => {
    if (scrollContainerRef.current) {
        const { scrollHeight, clientHeight } = scrollContainerRef.current
        // 直接操作 scrollTop 比 scrollIntoView 更稳
        scrollContainerRef.current.scrollTo({
            top: scrollHeight - clientHeight,
            behavior: behavior
        })
    }
  }

  // 1. 新消息加入时，平滑滚动
  useEffect(() => {
    // 只有当是新消息（非流式更新中）或者刚开始流式输出时滚动
    if (!loading || (loading && !hasFirstChunk)) {
        scrollToBottom('smooth')
    }
  }, [messages.length, loading, hasFirstChunk])

  // 2. AI 打字时，智能吸附
  useEffect(() => {
    if (loading && hasFirstChunk) {
        const container = scrollContainerRef.current
        if (container) {
            // 计算距离底部的距离
            const distance = container.scrollHeight - container.scrollTop - container.clientHeight
            
            // 如果用户正在看底部 (距离 < 100px)，则瞬间吸附，防止抖动
            if (distance < 100) {
                requestAnimationFrame(() => {
                    scrollToBottom('auto')
                })
            }
        }
    }
  }, [messages]) 

  // ==========================================

  /**
   * 发送消息（支持普通提问和划词追问）
   */
  const handleSend = async (refFragmentId?: string, selectedText?: string, queryOverride?: string) => {
    // 优先使用传入的 query，否则使用 input state
    const query = (queryOverride || input).trim()
    
    if (!query || loading) return

    // 只有在使用 input state 时才清空（避免清空追问输入）
    if (!queryOverride) {
      setInput('')
    }
    setError('')
    setLoading(true)
    setHasFirstChunk(false)

    // 先记录用户消息
    setUserMessages(prev => [...prev, query])

    // 为 AI 创建一条占位消息
    const parentId = messages.length > 0 ? messages[messages.length - 1].conversation_id : null
    const aiIndex = messages.length
    
    let currentConversationId = ''

    setMessages(prev => [
      ...prev,
      {
        answer: '',
        fragments: [],
        knowledge_triples: [],
        suggestion: undefined,
        conversation_id: '',
        parent_id: parentId,
      },
    ])

    try {
      await chatAPI.sendMessageStream(
        {
          query,
          parent_id: parentId,
          ref_fragment_id: refFragmentId || null,
          selected_text: selectedText || null,
          session_id: sessionId,
        },
        (payload: { type: string; text?: string; conversation_id?: string; parent_id?: string; answer?: string }) => {
          // 跟踪 conversation_id
          if (payload.conversation_id) {
            currentConversationId = payload.conversation_id
          }

          // 处理流式增量
          if (payload.type === 'meta' && payload.conversation_id) {
            // 更新占位消息的 conversation_id
            setMessages(prev => {
              const next = [...prev]
              if (next[aiIndex]) {
                next[aiIndex] = { ...next[aiIndex], conversation_id: payload.conversation_id as string }
              }
              return next
            })
          } else if (payload.type === 'delta' && payload.text) {
            // 收到首个增量，隐藏"思考中"
            setHasFirstChunk(true)
            setMessages(prev => {
              const next = [...prev]
              if (next[aiIndex]) {
                next[aiIndex] = { ...next[aiIndex], answer: (next[aiIndex].answer || '') + payload.text }
              }
              return next
            })
          } else if (payload.type === 'full' && payload.answer) {
            // 非流式划词追问路径：一次性完整返回
            setMessages(prev => {
              const next = [...prev]
              next[aiIndex] = {
                answer: payload.answer as string,
                fragments: [],
                knowledge_triples: [],
                suggestion: undefined,
                conversation_id: payload.conversation_id as string,
                parent_id: payload.parent_id as string | null | undefined,
              }
              return next
            })
          }
        }
      )

      // 流结束后，如果拿到了 conversation_id，则刷新思维导图
      // 延迟查询，等待 Neo4j 保存完成，并添加重试机制
      if (currentConversationId) {
        // 延迟 1 秒，给 Neo4j 保存留出时间
        setTimeout(async () => {
          try {
            // 最多重试 3 次
            let retries = 3
            let graphData = null
            
            while (retries > 0) {
              try {
                graphData = await mindMapAPI.getMindMap(currentConversationId)
                if (graphData && graphData.nodes && graphData.nodes.length > 0) {
                  setMindMapData(graphData)
                  if (!sidebarOpen) setSidebarOpen(true)
                  break // 成功获取数据，退出重试循环
                }
              } catch (err) {
                console.warn(`思维导图加载失败 (剩余重试 ${retries - 1} 次):`, err)
              }
              
              retries--
              if (retries > 0 && (!graphData || graphData.nodes.length === 0)) {
                // 等待 500ms 后重试
                await new Promise(resolve => setTimeout(resolve, 500))
              }
            }
            
            if (!graphData || graphData.nodes.length === 0) {
              console.warn('思维导图加载失败：重试 3 次后仍无数据')
            }
          } catch (err) {
            // 思维导图加载失败不影响主流程
            console.warn('思维导图加载失败:', err)
          }
        }, 1000) // 延迟 1 秒
      }
    } catch (error: any) {
      console.error('发送消息失败:', error)
      setUserMessages(prev => prev.slice(0, -1))

      if (error?.response?.status === 401) {
        authAPI.logout()
        navigate('/login')
      } else if (error?.response?.status === 404) {
        setError('聊天功能暂时不可用，请稍后再试')
      } else {
        setError('发送消息失败，请稍后再试')
      }
    } finally {
      setLoading(false)
    }
  }

  /**
   * 处理片段选择（划词追问）
   */
  const handleFragmentSelect = (fragmentId: string, selectedText: string) => {
    setSelectedFragmentId(fragmentId)
    setSelectedText(selectedText)
    setQuestionInput('')
    setQuestionModalOpen(true)
  }

  /**
   * 处理追问提交
   */
  const handleQuestionSubmit = async () => {
    if (!questionInput.trim()) return

    setQuestionModalOpen(false)
    // 直接传递 query，不依赖 state 更新
    handleSend(selectedFragmentId, selectedText, questionInput.trim())
  }

  /**
   * 处理追问取消
   */
  const handleQuestionCancel = () => {
    setQuestionModalOpen(false)
    setSelectedFragmentId('')
    setSelectedText('')
    setQuestionInput('')
  }

  /**
   * 处理键盘事件
   */
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  /**
   * 登出
   */
  const handleLogout = () => {
    authAPI.logout()
    navigate('/login')
  }

  // ==========================================
  // 👇👇👇 拖拽调整大小逻辑 👇👇👇
  // ==========================================

  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault()
    setIsResizing(true)
  }

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!isResizing || !containerRef.current) return
    
    const containerRect = containerRef.current.getBoundingClientRect()
    const newWidth = containerRect.right - e.clientX - 16 // 16px 是右侧 margin
    
    // 设置最小和最大宽度限制
    const minWidth = 300
    const maxWidth = containerRect.width * 0.6 // 最多占 60% 宽度
    
    if (newWidth >= minWidth && newWidth <= maxWidth) {
      setSidebarWidth(newWidth)
    }
  }, [isResizing])

  const handleMouseUp = useCallback(() => {
    setIsResizing(false)
  }, [])

  useEffect(() => {
    if (isResizing) {
      document.addEventListener('mousemove', handleMouseMove)
      document.addEventListener('mouseup', handleMouseUp)
      document.body.style.cursor = 'col-resize'
      document.body.style.userSelect = 'none'
      
      return () => {
        document.removeEventListener('mousemove', handleMouseMove)
        document.removeEventListener('mouseup', handleMouseUp)
        document.body.style.cursor = ''
        document.body.style.userSelect = ''
      }
    }
  }, [isResizing, handleMouseMove, handleMouseUp])

  // ==========================================

  // 样式定义
  const containerStyle: React.CSSProperties = {
    position: 'relative',
    display: 'flex',
    height: '100vh',
    width: '100vw', // 确保占满宽
    backgroundColor: 'transparent',
    overflow: 'hidden',
  }

  const backgroundStyle: React.CSSProperties = {
    position: 'fixed',
    top: 0,
    left: 0,
    width: '100%',
    height: '100%',
    backgroundImage: 'url(/bg.jpg)',
    backgroundSize: 'cover',
    backgroundPosition: 'center',
    backgroundRepeat: 'no-repeat',
    backgroundAttachment: 'fixed',
    filter: 'blur(10px)',
    opacity: 0.6,
    zIndex: -1,
  }

  // 👇👇👇 修复核心：显式指定高度，强制撑开！ 👇👇👇
  const mainAreaStyle: React.CSSProperties = {
    flex: sidebarOpen ? `0 0 calc(100% - ${sidebarWidth + 48}px)` : '1', // 48px 是 margin 总和
    display: 'flex',
    flexDirection: 'column',
    backgroundColor: 'rgba(255, 255, 255, 0.8)',
    margin: '16px',
    borderRadius: '8px',
    boxShadow: '0 2px 10px rgba(0,0,0,0.1)',
    overflow: 'hidden',
    position: 'relative',
    zIndex: 1,
    height: 'calc(100vh - 32px)', // 👈 这一行是救命稻草！
    minWidth: 0, // 允许收缩
    transition: sidebarOpen && !isResizing ? 'flex 0.3s' : 'none', // 只在关闭时过渡，调整大小时不过渡
  }

  const headerStyle: React.CSSProperties = {
    padding: '16px 24px',
    borderBottom: '1px solid #E5E7EB',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: 'white',
    flexShrink: 0,
  }

  const messagesAreaStyle: React.CSSProperties = {
    flex: 1,
    overflowY: 'auto',
    padding: '24px',
    backgroundColor: 'rgba(249, 250, 251, 0.6)',
    scrollBehavior: 'auto',
    minHeight: 0, // 防止 Flex 子项溢出
  }

  const userMessageStyle: React.CSSProperties = {
    display: 'flex',
    justifyContent: 'flex-end',
    marginBottom: '16px',
  }

  const userBubbleStyle: React.CSSProperties = {
    maxWidth: '70%',
    padding: '12px 16px',
    backgroundColor: '#2563EB',
    color: 'white',
    borderRadius: '12px 12px 4px 12px',
    fontSize: '16px',
    lineHeight: '1.5',
    wordWrap: 'break-word',
  }

  const aiMessageStyle: React.CSSProperties = {
    display: 'flex',
    justifyContent: 'flex-start',
    marginBottom: '24px',
  }

  const aiCardStyle: React.CSSProperties = {
    maxWidth: '85%',
    padding: '20px',
    backgroundColor: 'white',
    borderRadius: '8px',
    boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
    border: '1px solid #E5E7EB',
  }

  const inputAreaStyle: React.CSSProperties = {
    padding: '16px 24px',
    borderTop: '1px solid #E5E7EB',
    backgroundColor: 'white',
    display: 'flex',
    gap: '12px',
    alignItems: 'flex-end',
    flexShrink: 0,
  }

  const textareaStyle: React.CSSProperties = {
    flex: 1,
    padding: '12px 16px',
    border: '1px solid #D1D5DB',
    borderRadius: '8px',
    fontSize: '16px',
    fontFamily: 'inherit',
    resize: 'none',
    minHeight: '44px',
    maxHeight: '120px',
    outline: 'none',
    transition: 'border-color 0.2s',
  }

  const buttonStyle: React.CSSProperties = {
    padding: '12px 24px',
    backgroundColor: '#2563EB',
    color: 'white',
    border: 'none',
    borderRadius: '8px',
    fontSize: '16px',
    fontWeight: 500,
    cursor: loading || !input.trim() ? 'not-allowed' : 'pointer',
    opacity: loading || !input.trim() ? 0.6 : 1,
    transition: 'background-color 0.2s',
  }

  const sidebarStyle: React.CSSProperties = {
    width: sidebarOpen ? `${sidebarWidth}px` : '0',
    borderLeft: sidebarOpen ? '1px solid #E5E7EB' : 'none',
    backgroundColor: 'rgba(255, 255, 255, 0.9)',
    transition: isResizing ? 'none' : 'width 0.3s, border 0.3s', // 调整大小时不过渡
    overflow: 'hidden',
    display: 'flex',
    flexDirection: 'column',
    margin: '16px 16px 16px 0',
    borderRadius: '8px',
    boxShadow: '0 2px 10px rgba(0,0,0,0.1)',
    position: 'relative',
    zIndex: 1,
    height: 'calc(100vh - 32px)', // 侧边栏也加上这个高度，保持对齐
  }

  const resizerStyle: React.CSSProperties = {
    position: 'absolute',
    left: 0,
    top: 0,
    bottom: 0,
    width: '4px',
    backgroundColor: 'transparent',
    cursor: 'col-resize',
    zIndex: 10,
    transition: 'background-color 0.2s',
  }

  const errorStyle: React.CSSProperties = {
    padding: '12px 16px',
    marginBottom: '16px',
    backgroundColor: '#FEE2E2',
    color: '#EF4444',
    borderRadius: '8px',
    fontSize: '14px',
  }

  return (
    <div style={containerStyle} ref={containerRef}>
      {/* 背景层（模糊） */}
      <div style={backgroundStyle} />

      {/* 主聊天区域 */}
      <div style={mainAreaStyle}>
        {/* 头部 */}
        <div style={headerStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <h1 style={{ fontSize: '20px', fontWeight: 600, color: '#111827', margin: 0 }}>
              DeepStudy
            </h1>
            <span style={{ fontSize: '14px', color: '#6B7280' }}>
              递归学习助手
            </span>
          </div>
          <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              style={{
                padding: '8px 16px',
                border: '1px solid #D1D5DB',
                borderRadius: '6px',
                backgroundColor: 'white',
                cursor: 'pointer',
                fontSize: '14px',
                color: '#111827',
              }}
              onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#F3F4F6'}
              onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'white'}
            >
              {sidebarOpen ? '隐藏图谱' : '显示图谱'}
            </button>
            <button
              onClick={handleLogout}
              style={{
                padding: '8px 16px',
                border: '1px solid #D1D5DB',
                borderRadius: '6px',
                backgroundColor: 'white',
                cursor: 'pointer',
                fontSize: '14px',
                color: '#111827',
              }}
              onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#F3F4F6'}
              onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'white'}
            >
              登出
            </button>
          </div>
        </div>

        {/* 绑定滚动容器 Ref */}
        <div style={messagesAreaStyle} ref={scrollContainerRef}>
          {messages.length === 0 && (
            <div style={{
              textAlign: 'center',
              color: '#6B7280',
              marginTop: '100px',
            }}>
              <h2 style={{ fontSize: '24px', marginBottom: '8px', color: '#111827' }}>
                开始你的学习之旅
              </h2>
              <p>输入你的问题，AI 助手会帮助你深入理解</p>
            </div>
          )}

          {messages.map((msg, index) => (
            <div key={index}>
              {/* 用户消息 */}
              {userMessages[index] && (
                <div style={userMessageStyle}>
                  <div style={userBubbleStyle}>
                    {userMessages[index]}
                  </div>
                </div>
              )}

              {/* AI 回答 */}
              <div style={aiMessageStyle}>
                <div style={aiCardStyle}>
                  {msg.answer ? (
                      <TextFragment
                        content={msg.answer}
                        fragments={msg.fragments || []}
                        onFragmentSelect={handleFragmentSelect}
                      />
                    ) : loading && !hasFirstChunk && index === messages.length - 1 ? (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#6B7280' }}>
                          <div style={{
                            width: '16px',
                            height: '16px',
                            border: '2px solid #E5E7EB',
                            borderTopColor: '#2563EB',
                            borderRadius: '50%',
                            animation: 'spin 1s linear infinite',
                          }} />
                          <span>思考中...</span>
                        </div>
                    ) : null}
                </div>
              </div>
            </div>
          ))}

          {/* 错误提示 */}
          {error && <div style={errorStyle} role="alert">{error}</div>}

          <div ref={messagesEndRef} />
        </div>

        {/* 输入区域 */}
        <div style={inputAreaStyle}>
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => {
              setInput(e.target.value)
              setError('')
            }}
            onKeyDown={handleKeyDown}
            placeholder="输入你的问题... (Enter 发送, Shift+Enter 换行)"
            disabled={loading}
            style={{
              ...textareaStyle,
              ...(loading ? { backgroundColor: '#F3F4F6', cursor: 'not-allowed' } : {}),
            }}
            onFocus={(e) => {
              e.target.style.borderColor = '#2563EB'
              e.target.style.boxShadow = '0 0 0 3px rgba(37, 99, 235, 0.1)'
            }}
            onBlur={(e) => {
              e.target.style.borderColor = '#D1D5DB'
              e.target.style.boxShadow = 'none'
            }}
            rows={1}
          />
          <button
            onClick={() => handleSend()}
            disabled={loading || !input.trim()}
            style={buttonStyle}
            onMouseEnter={(e) => {
              if (!loading && input.trim()) {
                e.currentTarget.style.backgroundColor = '#1D4ED8'
              }
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = '#2563EB'
            }}
          >
            {loading ? '发送中...' : '发送'}
          </button>
        </div>
      </div>

      {/* 思维导图侧边栏 */}
      {sidebarOpen && (
        <div style={sidebarStyle}>
          {/* 可拖拽的分隔条 */}
          <div
            style={isResizing ? { ...resizerStyle, backgroundColor: '#2563EB' } : resizerStyle}
            onMouseDown={handleMouseDown}
            onMouseEnter={(e) => {
              if (!isResizing) {
                e.currentTarget.style.backgroundColor = '#E5E7EB'
              }
            }}
            onMouseLeave={(e) => {
              if (!isResizing) {
                e.currentTarget.style.backgroundColor = 'transparent'
              }
            }}
          />
          
          <div style={{
            padding: '16px',
            borderBottom: '1px solid #E5E7EB',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}>
            <h3 style={{ fontSize: '18px', fontWeight: 600, margin: 0, color: '#111827' }}>
              知识图谱
            </h3>
            <button
              onClick={() => setSidebarOpen(false)}
              style={{
                padding: '4px 8px',
                border: 'none',
                backgroundColor: 'transparent',
                cursor: 'pointer',
                fontSize: '20px',
                color: '#6B7280',
              }}
              onMouseEnter={(e) => e.currentTarget.style.color = '#111827'}
              onMouseLeave={(e) => e.currentTarget.style.color = '#6B7280'}
            >
              ×
            </button>
          </div>
          <div style={{ flex: 1, padding: '16px', overflow: 'hidden' }}>
            <KnowledgeGraph data={mindMapData} />
          </div>
        </div>
      )}

      {/* 追问弹窗 */}
      {questionModalOpen && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.5)',
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            zIndex: 1000,
          }}
          onClick={handleQuestionCancel}
        >
          <div
            style={{
              backgroundColor: 'white',
              borderRadius: '12px',
              padding: '24px',
              maxWidth: '500px',
              width: '90%',
              maxHeight: '80vh',
              overflowY: 'auto',
              boxShadow: '0 10px 25px rgba(0, 0, 0, 0.15)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ marginBottom: '20px' }}>
              <h2 style={{ fontSize: '20px', fontWeight: 600, margin: 0, color: '#111827' }}>
                追问关于选中内容
              </h2>
              <p style={{ fontSize: '14px', color: '#6B7280', marginTop: '8px' }}>
                对以下选中的内容进行深入追问
              </p>
            </div>

            {/* 选中的文本预览 */}
            <div
              style={{
                backgroundColor: '#F3F4F6',
                padding: '16px',
                borderRadius: '8px',
                marginBottom: '20px',
                fontSize: '14px',
                lineHeight: '1.5',
                borderLeft: '4px solid #2563EB',
              }}
            >
              {selectedText}
            </div>

            {/* 问题输入 */}
            <div style={{ marginBottom: '24px' }}>
              <label
                style={{
                  display: 'block',
                  fontSize: '14px',
                  fontWeight: 500,
                  color: '#374151',
                  marginBottom: '8px',
                }}
              >
                你的问题
              </label>
              <textarea
                value={questionInput}
                onChange={(e) => setQuestionInput(e.target.value)}
                placeholder="输入你想了解的问题..."
                style={{
                  width: '100%',
                  padding: '12px',
                  border: '1px solid #D1D5DB',
                  borderRadius: '8px',
                  fontSize: '14px',
                  lineHeight: '1.5',
                  resize: 'vertical',
                  minHeight: '80px',
                  fontFamily: 'inherit',
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                    handleQuestionSubmit()
                  }
                }}
              />
            </div>

            {/* 操作按钮 */}
            <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
              <button
                onClick={handleQuestionCancel}
                style={{
                  padding: '10px 20px',
                  border: '1px solid #D1D5DB',
                  borderRadius: '8px',
                  backgroundColor: 'white',
                  color: '#374151',
                  cursor: 'pointer',
                  fontSize: '14px',
                  fontWeight: 500,
                  transition: 'all 0.2s',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = '#F3F4F6'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = 'white'
                }}
              >
                取消
              </button>
              <button
                onClick={handleQuestionSubmit}
                disabled={!questionInput.trim()}
                style={{
                  padding: '10px 20px',
                  border: 'none',
                  borderRadius: '8px',
                  backgroundColor: questionInput.trim() ? '#2563EB' : '#93C5FD',
                  color: 'white',
                  cursor: questionInput.trim() ? 'pointer' : 'not-allowed',
                  fontSize: '14px',
                  fontWeight: 500,
                  transition: 'all 0.2s',
                }}
                onMouseEnter={(e) => {
                  if (questionInput.trim()) {
                    e.currentTarget.style.backgroundColor = '#1D4ED8'
                  }
                }}
                onMouseLeave={(e) => {
                  if (questionInput.trim()) {
                    e.currentTarget.style.backgroundColor = '#2563EB'
                  }
                }}
              >
                提交追问
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default ChatInterface
