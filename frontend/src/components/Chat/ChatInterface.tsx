<<<<<<< HEAD
import { useState, useEffect, useRef } from 'react'
=======
import { useState, useEffect, useRef, useLayoutEffect } from 'react'
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
import { useNavigate } from 'react-router-dom'
import { authAPI, chatAPI, mindMapAPI } from '../../services/api'
import { AgentResponse, MindMapGraph } from '../../types/api'
import TextFragment from '../Markdown/TextFragment'
import KnowledgeGraph from '../MindMap/KnowledgeGraph'

<<<<<<< HEAD
/**
 * 聊天界面主组件
 * 包含对话展示、输入框、思维导图侧边栏
 */
const ChatInterface = () => {
  const navigate = useNavigate()
=======
const ChatInterface = () => {
  const navigate = useNavigate()
  
  const scrollContainerRef = useRef<HTMLDivElement>(null)
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  
  const [messages, setMessages] = useState<AgentResponse[]>([])
  const [userMessages, setUserMessages] = useState<string[]>([])
  const [input, setInput] = useState<string>('')
  const [loading, setLoading] = useState<boolean>(false)
  const [hasFirstChunk, setHasFirstChunk] = useState<boolean>(false)
  const [error, setError] = useState<string>('')
  const [mindMapData, setMindMapData] = useState<MindMapGraph>({ nodes: [], edges: [] })
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(true)
  const [sessionId] = useState<string>(() => `session_${Date.now()}`)
<<<<<<< HEAD
  const [questionModalOpen, setQuestionModalOpen] = useState(false)
  const [selectedFragmentId, setSelectedFragmentId] = useState<string>('')
  const [selectedText, setSelectedText] = useState<string>('')
  const [questionInput, setQuestionInput] = useState<string>('')

  /**
   * 自动滚动到底部
   */
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages, loading])

  /**
   * 发送消息（支持普通提问和划词追问）
   */
  const handleSend = async (refFragmentId?: string, selectedText?: string) => {
=======

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

  const handleSend = async (refFragmentId?: string) => {
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
    if (!input.trim() || loading) return

    const query = input.trim()
    setInput('')
    setError('')
    setLoading(true)
    setHasFirstChunk(false)

<<<<<<< HEAD
    // 先记录用户消息
    setUserMessages(prev => [...prev, query])

    // 为 AI 创建一条占位消息
    const parentId = messages.length > 0 ? messages[messages.length - 1].conversation_id : null
    const aiIndex = messages.length
=======
    setUserMessages(prev => [...prev, query])

    const parentId = messages.length > 0 ? messages[messages.length - 1].conversation_id : null
    const aiIndex = messages.length
    
    let currentConversationId = ''; 

>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
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
<<<<<<< HEAD
          selected_text: selectedText || null,
          session_id: sessionId,
        },
        (payload: { type: string; text?: string; conversation_id?: string; parent_id?: string; answer?: string }) => {
          // 处理流式增量
          if (payload.type === 'meta' && payload.conversation_id) {
            // 更新占位消息的 conversation_id
            setMessages(prev => {
              const next = [...prev]
              const target = next[aiIndex]
              if (target) {
                next[aiIndex] = {
                  ...target,
                  conversation_id: payload.conversation_id as string,
                }
=======
          session_id: sessionId,
        },
        (payload: { type: string; text?: string; conversation_id?: string; parent_id?: string; answer?: string }) => {
          
          if (payload.conversation_id) {
            currentConversationId = payload.conversation_id;
          }

          if (payload.type === 'meta' && payload.conversation_id) {
            setMessages(prev => {
              const next = [...prev]
              if (next[aiIndex]) {
                next[aiIndex] = { ...next[aiIndex], conversation_id: payload.conversation_id as string }
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
              }
              return next
            })
          } else if (payload.type === 'delta' && payload.text) {
<<<<<<< HEAD
            // 收到首个增量，隐藏“思考中”
            setHasFirstChunk(true)
            setMessages(prev => {
              const next = [...prev]
              const target = next[aiIndex]
              if (target) {
                next[aiIndex] = {
                  ...target,
                  answer: (target.answer || '') + payload.text,
                }
=======
            setHasFirstChunk(true)
            setMessages(prev => {
              const next = [...prev]
              if (next[aiIndex]) {
                next[aiIndex] = { ...next[aiIndex], answer: (next[aiIndex].answer || '') + payload.text }
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
              }
              return next
            })
          } else if (payload.type === 'full' && payload.answer) {
<<<<<<< HEAD
            // 非流式划词追问路径：一次性完整返回
=======
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
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

<<<<<<< HEAD
      // 流结束后，如果拿到了 conversation_id，则刷新思维导图
      // 直接使用外部的messages状态，确保获取到最新的消息
      const finalMsg = messages[aiIndex]
      if (finalMsg && finalMsg.conversation_id) {
        try {
          console.log('获取知识图谱数据，conversation_id:', finalMsg.conversation_id)
          const graphData = await mindMapAPI.getMindMap(finalMsg.conversation_id)
          console.log('知识图谱数据获取成功:', graphData)
          setMindMapData(graphData)
          console.log('知识图谱数据已更新')
        } catch (err) {
          // 思维导图加载失败不影响主流程
          console.warn('思维导图加载失败:', err)
        }
      } else {
        console.log('未获取到conversation_id，无法加载知识图谱')
        console.log('当前消息:', finalMsg)
      }
=======
      if (currentConversationId) {
        try {
          const graphData = await mindMapAPI.getMindMap(currentConversationId)
          if (graphData && graphData.nodes && graphData.nodes.length > 0) {
            setMindMapData(graphData)
            if (!sidebarOpen) setSidebarOpen(true);
          }
        } catch (err) {
          console.warn('思维导图加载失败:', err)
        }
      }

>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
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

<<<<<<< HEAD
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
    setInput(questionInput)
    
    setTimeout(() => {
      handleSend(selectedFragmentId, selectedText)
    }, 0)
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
=======
  const handleFragmentSelect = (fragmentId: string) => {
    const query = prompt('请输入你的问题:')
    if (query && messages.length > 0) {
      setInput(query)
      setTimeout(() => {
        handleSend(fragmentId)
      }, 0)
    }
  }

>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

<<<<<<< HEAD
  /**
   * 登出
   */
=======
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
  const handleLogout = () => {
    authAPI.logout()
    navigate('/login')
  }

<<<<<<< HEAD
  // 样式常量
=======
  // 样式定义
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
  const containerStyle: React.CSSProperties = {
    position: 'relative',
    display: 'flex',
    height: '100vh',
<<<<<<< HEAD
    backgroundColor: 'transparent',
=======
    width: '100vw', // 确保占满宽
    backgroundColor: 'transparent',
    overflow: 'hidden'
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
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

<<<<<<< HEAD
=======
  // 👇👇👇 修复核心：显式指定高度，强制撑开！ 👇👇👇
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
  const mainAreaStyle: React.CSSProperties = {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    backgroundColor: 'rgba(255, 255, 255, 0.8)',
    margin: '16px',
    borderRadius: '8px',
    boxShadow: '0 2px 10px rgba(0,0,0,0.1)',
    overflow: 'hidden',
    position: 'relative',
    zIndex: 1,
<<<<<<< HEAD
=======
    height: 'calc(100vh - 32px)' // 👈 这一行是救命稻草！
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
  }

  const headerStyle: React.CSSProperties = {
    padding: '16px 24px',
    borderBottom: '1px solid #E5E7EB',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: 'white',
<<<<<<< HEAD
=======
    flexShrink: 0,
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
  }

  const messagesAreaStyle: React.CSSProperties = {
    flex: 1,
    overflowY: 'auto',
    padding: '24px',
    backgroundColor: 'rgba(249, 250, 251, 0.6)',
<<<<<<< HEAD
=======
    scrollBehavior: 'auto',
    minHeight: 0 // 防止 Flex 子项溢出
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
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
<<<<<<< HEAD
=======
    flexShrink: 0,
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
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
    width: sidebarOpen ? '400px' : '0',
    borderLeft: sidebarOpen ? '1px solid #E5E7EB' : 'none',
    backgroundColor: 'rgba(255, 255, 255, 0.9)',
    transition: 'width 0.3s',
    overflow: 'hidden',
    display: 'flex',
    flexDirection: 'column',
    margin: '16px 16px 16px 0',
    borderRadius: '8px',
    boxShadow: '0 2px 10px rgba(0,0,0,0.1)',
    position: 'relative',
    zIndex: 1,
<<<<<<< HEAD
=======
    height: 'calc(100vh - 32px)' // 侧边栏也加上这个高度，保持对齐
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
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
    <div style={containerStyle}>
<<<<<<< HEAD
      {/* 背景层（模糊） */}
      <div style={backgroundStyle} />

      {/* 主聊天区域 */}
      <div style={mainAreaStyle}>
        {/* 头部 */}
=======
      <div style={backgroundStyle} />

      <div style={mainAreaStyle}>
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
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
<<<<<<< HEAD
              onMouseEnter={(e) => {
                e.currentTarget.style.backgroundColor = '#F3F4F6'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.backgroundColor = 'white'
              }}
=======
              onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#F3F4F6'}
              onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'white'}
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
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
<<<<<<< HEAD
              onMouseEnter={(e) => {
                e.currentTarget.style.backgroundColor = '#F3F4F6'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.backgroundColor = 'white'
              }}
=======
              onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#F3F4F6'}
              onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'white'}
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
            >
              登出
            </button>
          </div>
        </div>

<<<<<<< HEAD
        {/* 消息列表 */}
        <div style={messagesAreaStyle}>
=======
        {/* 绑定滚动容器 Ref */}
        <div style={messagesAreaStyle} ref={scrollContainerRef}>
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
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
<<<<<<< HEAD
              {/* 用户消息 */}
=======
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
              {userMessages[index] && (
                <div style={userMessageStyle}>
                  <div style={userBubbleStyle}>
                    {userMessages[index]}
                  </div>
                </div>
              )}

<<<<<<< HEAD
              {/* AI 回答 */}
              <div style={aiMessageStyle}>
                <div style={aiCardStyle}>
                  {msg.answer
                    ? (
=======
              <div style={aiMessageStyle}>
                <div style={aiCardStyle}>
                  {msg.answer ? (
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
                      <TextFragment
                        content={msg.answer}
                        fragments={msg.fragments || []}
                        onFragmentSelect={handleFragmentSelect}
                      />
<<<<<<< HEAD
                    )
                    : loading && !hasFirstChunk && index === messages.length - 1
                      ? (
=======
                    ) : loading && !hasFirstChunk && index === messages.length - 1 ? (
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#6B7280' }}>
                          <div style={{
                            width: '16px',
                            height: '16px',
                            border: '2px solid #E5E7EB',
                            borderTopColor: '#2563EB',
                            borderRadius: '50%',
                            animation: 'spin 1s linear infinite',
<<<<<<< HEAD
                          }}
                          />
                          <span>思考中...</span>
                        </div>
                        )
                      : null}
=======
                          }} />
                          <span>思考中...</span>
                        </div>
                    ) : null}
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
                </div>
              </div>
            </div>
          ))}

<<<<<<< HEAD
          {/* 错误提示 */}
          {error && (
            <div style={errorStyle} role="alert">
              {error}
            </div>
          )}
=======
          {error && <div style={errorStyle} role="alert">{error}</div>}
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45

          <div ref={messagesEndRef} />
        </div>

<<<<<<< HEAD
        {/* 输入区域 */}
=======
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
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
<<<<<<< HEAD
              if (!loading && input.trim()) {
                e.currentTarget.style.backgroundColor = '#1D4ED8'
              }
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = '#2563EB'
            }}
=======
              if (!loading && input.trim()) e.currentTarget.style.backgroundColor = '#1D4ED8'
            }}
            onMouseLeave={(e) => e.currentTarget.style.backgroundColor = '#2563EB'}
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
          >
            {loading ? '发送中...' : '发送'}
          </button>
        </div>
      </div>

<<<<<<< HEAD
      {/* 思维导图侧边栏 */}
=======
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
      {sidebarOpen && (
        <div style={sidebarStyle}>
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
<<<<<<< HEAD
              onMouseEnter={(e) => {
                e.currentTarget.style.color = '#111827'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.color = '#6B7280'
              }}
=======
              onMouseEnter={(e) => e.currentTarget.style.color = '#111827'}
              onMouseLeave={(e) => e.currentTarget.style.color = '#6B7280'}
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
            >
              ×
            </button>
          </div>
          <div style={{ flex: 1, padding: '16px' }}>
            <KnowledgeGraph data={mindMapData} />
          </div>
        </div>
      )}
<<<<<<< HEAD

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
=======
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
    </div>
  )
}

<<<<<<< HEAD
export default ChatInterface
=======
export default ChatInterface
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
