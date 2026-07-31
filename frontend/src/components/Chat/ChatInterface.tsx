import { useState, useEffect, useRef, useCallback } from 'react'
import axios from 'axios'
import { chatAPI, mindMapAPI, profileAPI } from '../../services/api'
import { AgentResponse, MindMapGraph, MindMapNode, MindMapEdge, ConceptProfileSummary } from '../../types/api'
import TextFragment from '../Markdown/TextFragment'
import KnowledgeGraph from '../MindMap/KnowledgeGraph'

const ChatInterface = () => {
  // --- 基础 Refs ---
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  
  // --- 基础 State ---
  const [messages, setMessages] = useState<AgentResponse[]>([])
  const [userMessages, setUserMessages] = useState<string[]>([])
  const [input, setInput] = useState<string>('')
  const [loading, setLoading] = useState<boolean>(false)
  const [hasFirstChunk, setHasFirstChunk] = useState<boolean>(false)
  const [error, setError] = useState<string>('')
  
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(true)
  const [sidebarWidth, setSidebarWidth] = useState<number>(400)
  const [isResizing, setIsResizing] = useState<boolean>(false)
  const [sessionId] = useState<string>(() => `session_${Date.now()}`)
  
  const [questionModalOpen, setQuestionModalOpen] = useState(false)
  const [selectedFragmentId, setSelectedFragmentId] = useState<string>('')
  const [selectedText, setSelectedText] = useState<string>('')
  const [questionInput, setQuestionInput] = useState<string>('')

  const [profileModalOpen, setProfileModalOpen] = useState(false)
  const [profileList, setProfileList] = useState<ConceptProfileSummary[]>([])
  const [profileLoading, setProfileLoading] = useState(false)
  const [profileError, setProfileError] = useState<string>('')
  const [planList, setPlanList] = useState<string[]>([])

  // ⭐⭐⭐ 核心 State ⭐⭐⭐
  // 1. mindMapData: 最终展示给用户的完整大图
  const [mindMapData, setMindMapData] = useState<MindMapGraph>({ nodes: [], edges: [] })
  
  // 2. currentPollingId: 当前正在发生的对话 ID (每次提问都会变)
  const [currentPollingId, setCurrentPollingId] = useState<string | null>(null)

  // ==========================================
  // 👇👇👇 核心逻辑：增量合并算法 👇👇👇
  // ==========================================
  
  // 这个函数负责把“新来的数据”缝合到“旧数据”上
  const mergeData = (oldData: MindMapGraph, newData: MindMapGraph): MindMapGraph => {
    // 1. 分离系统节点和用户节点
    const userNodes = oldData.nodes.filter(n => n.id.startsWith('node_')); // 以'node_'开头的是用户节点
    
    const userEdges = oldData.edges.filter(e => e.id.startsWith('edge_')); // 以'edge_'开头的是用户边

    // 2. 建立 Map 用于去重新数据 (ID 为 Key)
    const nodeMap = new Map<string, MindMapNode>();
    const edgeMap = new Map<string, MindMapEdge>();

    // 3. 先把用户节点和用户边放进去（这些需要保留）
    userNodes.forEach(n => nodeMap.set(n.id, n));
    userEdges.forEach(e => {
      // 使用稳定的键值，避免因为顺序变化导致的冲突
      const edgeKey = `${e.source}-${e.target}`;
      edgeMap.set(edgeKey, e);
    });

    // 4. 再把新数据放进去 (系统数据)
    newData.nodes.forEach(n => {
        // 🎨 样式补丁：如果是第一个节点，给它 root 样式；其他的给 explanation 样式
        // 这样可以保证根节点永远是蓝色的，新长出来的都是橙色的
        const variant = nodeMap.size === 0 ? 'root' : 'explanation';
        
        // 如果这个节点已经存在且有了 variant，保留原来的；否则用新的
        const existing = nodeMap.get(n.id);
        const finalVariant = existing?.data?.variant || n.data?.variant || variant;

        nodeMap.set(n.id, {
            ...n,
            data: { ...n.data, variant: finalVariant }
        });
    });

    // 5. 处理新边，确保它们引用的节点存在
    newData.edges.forEach(e => {
      // 检查源节点和目标节点是否都存在
      if (nodeMap.has(e.source) && nodeMap.has(e.target)) {
        const edgeKey = `${e.source}-${e.target}`;
        edgeMap.set(edgeKey, e);
      }
    });

    // 6. 返回合并后的结果（包含用户节点和新系统数据）
    return {
        nodes: Array.from(nodeMap.values()),
        edges: Array.from(edgeMap.values())
    };
  };

  // 轮询 Effect
  useEffect(() => {
    // 只有当有 ID 且侧边栏打开时才轮询
    if (!currentPollingId || !sidebarOpen) return;

    let isMounted = true;

    const fetchAndMerge = async () => {
      try {
        // 只查当前最新的 ID (因为后端这次已经修复了，查子 ID 也能返回它周围的数据)
        const data = await mindMapAPI.getMindMap(currentPollingId);
        
        if (isMounted && data && data.nodes && data.nodes.length > 0) {
          setMindMapData(prev => {
            // 执行合并
            const merged = mergeData(prev, data);
            
            // 检查是否有实质性变化，避免不必要的更新
            const hasNewNodes = merged.nodes.some(n => !prev.nodes.some(pn => pn.id === n.id));
            const hasNewEdges = merged.edges.some(e => !prev.edges.some(pe => pe.id === e.id));
            const hasDifferentLength = merged.nodes.length !== prev.nodes.length || merged.edges.length !== prev.edges.length;
            
            if (hasNewNodes || hasNewEdges || hasDifferentLength) {
                // console.log(`图谱更新: 从 ${prev.nodes.length} -> ${merged.nodes.length} 个节点`);
                return merged;
            }
            return prev;
          });
        }
      } catch (err) {
        // 轮询出错不报错，静默重试
        console.error('获取思维导图数据失败:', err);
      }
    };

    // 立即执行一次
    fetchAndMerge();

    // 每 2 秒轮询一次 (频率稍微调高一点，让你能更快看到结果)
    const interval = setInterval(fetchAndMerge, 2000);

    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [currentPollingId, sidebarOpen]); // 只要 ID 变了，就立刻开始查新 ID

  // ==========================================

  const scrollToBottom = (behavior: 'auto' | 'smooth' = 'smooth') => {
    if (scrollContainerRef.current) {
        const { scrollHeight, clientHeight } = scrollContainerRef.current
        scrollContainerRef.current.scrollTo({
            top: scrollHeight - clientHeight,
            behavior: behavior
        })
    }
  }

  useEffect(() => {
    if (!loading || (loading && !hasFirstChunk)) {
        scrollToBottom('smooth')
    }
  }, [messages.length, loading, hasFirstChunk])

  useEffect(() => {
    if (loading && hasFirstChunk) {
        const container = scrollContainerRef.current
        if (container) {
            const distance = container.scrollHeight - container.scrollTop - container.clientHeight
            if (distance < 100) {
                requestAnimationFrame(() => {
                    scrollToBottom('auto')
                })
            }
        }
    }
  }, [messages, loading, hasFirstChunk])

  const handleSend = async (refFragmentId?: string, selectedText?: string, queryOverride?: string) => {
    const query = (queryOverride || input).trim()
    if (!query || loading) return

    if (!queryOverride) setInput('')
    setError('')
    setLoading(true)
    setHasFirstChunk(false)

    setUserMessages(prev => [...prev, query])

    const parentId = messages.length > 0 ? messages[messages.length - 1].conversation_id : null
    const aiIndex = messages.length
    
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
          
          if (payload.conversation_id) {
            // ⭐ 核心逻辑：只要有了新 ID，就立刻把它设为当前轮询目标
            // 剩下的交给 useEffect 去把它抓回来并合并
            setCurrentPollingId(payload.conversation_id as string);
            
            if (!sidebarOpen) setSidebarOpen(true);
          }

          if (payload.type === 'meta' && payload.conversation_id) {
            setMessages(prev => {
              const next = [...prev]
              if (next[aiIndex]) {
                next[aiIndex] = { ...next[aiIndex], conversation_id: payload.conversation_id as string }
              }
              return next
            })
          } else if (payload.type === 'delta' && payload.text) {
            setHasFirstChunk(true)
            setMessages(prev => {
              const next = [...prev]
              if (next[aiIndex]) {
                next[aiIndex] = { ...next[aiIndex], answer: (next[aiIndex].answer || '') + payload.text }
              }
              return next
            })
          } else if (payload.type === 'full' && payload.answer) {
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

    } catch (error: unknown) {
      console.error('发送消息失败:', error)
      setUserMessages(prev => prev.slice(0, -1))
      if (axios.isAxiosError(error) && error.response?.status === 404) {
        setError('聊天功能暂时不可用，请稍后再试')
      } else {
        setError('发送消息失败，请稍后再试')
      }
    } finally {
      setLoading(false)
    }
  }

  // ... (剩余的UI辅助代码保持不变) ...
  const handleFragmentSelect = (fragmentId: string, selectedText: string) => {
    setSelectedFragmentId(fragmentId)
    setSelectedText(selectedText)
    setQuestionInput('')
    setQuestionModalOpen(true)
  }

  const handleProfileOpen = useCallback(async () => {
    setProfileModalOpen(true)
    setProfileError('')
    setProfileLoading(true)
    try {
      const [list, plan] = await Promise.all([profileAPI.getSummary(), profileAPI.getPlan()])
      setProfileList(list)
      setPlanList(plan)
    } catch (e: unknown) {
      setProfileList([])
      setProfileError(e instanceof Error ? e.message : '加载画像失败')
    } finally {
      setProfileLoading(false)
    }
  }, [])

  useEffect(() => {
    profileAPI.getPlan().then(setPlanList).catch(() => {})
  }, [])

  const handleQuestionSubmit = async () => {
    if (!questionInput.trim()) return
    setQuestionModalOpen(false)
    handleSend(selectedFragmentId, selectedText, questionInput.trim())
  }

  const handleQuestionCancel = () => {
    setQuestionModalOpen(false)
    setSelectedFragmentId('')
    setSelectedText('')
    setQuestionInput('')
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault()
    setIsResizing(true)
  }

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!isResizing || !containerRef.current) return
    const containerRect = containerRef.current.getBoundingClientRect()
    const newWidth = containerRect.right - e.clientX - 16
    const minWidth = 300
    const maxWidth = containerRect.width * 0.6
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

  const containerStyle: React.CSSProperties = {
    position: 'relative',
    display: 'flex',
    height: '100vh',
    width: '100vw',
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
  const mainAreaStyle: React.CSSProperties = {
    flex: sidebarOpen ? `0 0 calc(100% - ${sidebarWidth + 48}px)` : '1',
    display: 'flex',
    flexDirection: 'column',
    backgroundColor: 'rgba(255, 255, 255, 0.8)',
    margin: '16px',
    borderRadius: '8px',
    boxShadow: '0 2px 10px rgba(0,0,0,0.1)',
    overflow: 'hidden',
    position: 'relative',
    zIndex: 1,
    height: 'calc(100vh - 32px)',
    minWidth: 0,
    transition: sidebarOpen && !isResizing ? 'flex 0.3s' : 'none',
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
    minHeight: 0,
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
    transition: isResizing ? 'none' : 'width 0.3s, border 0.3s',
    overflow: 'hidden',
    display: 'flex',
    flexDirection: 'column',
    margin: '16px 16px 16px 0',
    borderRadius: '8px',
    boxShadow: '0 2px 10px rgba(0,0,0,0.1)',
    position: 'relative',
    zIndex: 1,
    height: 'calc(100vh - 32px)',
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
      <div style={backgroundStyle} />
      <div style={mainAreaStyle}>
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
              onClick={handleProfileOpen}
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
              学习画像
            </button>
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
          </div>
        </div>

        <div style={messagesAreaStyle} ref={scrollContainerRef}>
          {messages.length === 0 && (
            <div style={{ textAlign: 'center', color: '#6B7280', marginTop: '100px' }}>
              <h2 style={{ fontSize: '24px', marginBottom: '8px', color: '#111827' }}>
                开始你的学习之旅
              </h2>
              <p>输入你的问题，AI 助手会帮助你深入理解</p>
            </div>
          )}
          {messages.map((msg, index) => (
            <div key={index}>
              {userMessages[index] && (
                <div style={userMessageStyle}>
                  <div style={userBubbleStyle}>
                    {userMessages[index]}
                  </div>
                </div>
              )}
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
          {error && <div style={errorStyle} role="alert">{error}</div>}
          <div ref={messagesEndRef} />
        </div>

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

      {sidebarOpen && (
        <div style={sidebarStyle}>
          <div
            style={isResizing ? { ...resizerStyle, backgroundColor: '#2563EB' } : resizerStyle}
            onMouseDown={handleMouseDown}
            onMouseEnter={(e) => {
              if (!isResizing) e.currentTarget.style.backgroundColor = '#E5E7EB'
            }}
            onMouseLeave={(e) => {
              if (!isResizing) e.currentTarget.style.backgroundColor = 'transparent'
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
            <KnowledgeGraph data={mindMapData} planConcepts={planList} />
          </div>
        </div>
      )}

      {questionModalOpen && (
        <div
          style={{
            position: 'fixed',
            top: 0, left: 0, right: 0, bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.5)',
            display: 'flex', justifyContent: 'center', alignItems: 'center', zIndex: 1000,
          }}
          onClick={handleQuestionCancel}
        >
          <div
            style={{
              backgroundColor: 'white', borderRadius: '12px', padding: '24px',
              maxWidth: '500px', width: '90%', maxHeight: '80vh', overflowY: 'auto',
              boxShadow: '0 10px 25px rgba(0, 0, 0, 0.15)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ marginBottom: '20px' }}>
              <h2 style={{ fontSize: '20px', fontWeight: 600, margin: 0, color: '#111827' }}>追问关于选中内容</h2>
              <p style={{ fontSize: '14px', color: '#6B7280', marginTop: '8px' }}>对以下选中的内容进行深入追问</p>
            </div>
            <div style={{ backgroundColor: '#F3F4F6', padding: '16px', borderRadius: '8px', marginBottom: '20px', fontSize: '14px', lineHeight: '1.5', borderLeft: '4px solid #2563EB' }}>
              {selectedText}
            </div>
            <div style={{ marginBottom: '24px' }}>
              <label style={{ display: 'block', fontSize: '14px', fontWeight: 500, color: '#374151', marginBottom: '8px' }}>你的问题</label>
              <textarea value={questionInput} onChange={(e) => setQuestionInput(e.target.value)} placeholder="输入你想了解的问题..." style={{ width: '100%', padding: '12px', border: '1px solid #D1D5DB', borderRadius: '8px', fontSize: '14px', lineHeight: '1.5', resize: 'vertical', minHeight: '80px', fontFamily: 'inherit' }} onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { handleQuestionSubmit() } }} />
            </div>
            <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
              <button onClick={handleQuestionCancel} style={{ padding: '10px 20px', border: '1px solid #D1D5DB', borderRadius: '8px', backgroundColor: 'white', color: '#374151', cursor: 'pointer', fontSize: '14px', fontWeight: 500 }} onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#F3F4F6'} onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'white'}>取消</button>
              <button onClick={handleQuestionSubmit} disabled={!questionInput.trim()} style={{ padding: '10px 20px', border: 'none', borderRadius: '8px', backgroundColor: questionInput.trim() ? '#2563EB' : '#93C5FD', color: 'white', cursor: questionInput.trim() ? 'pointer' : 'not-allowed', fontSize: '14px', fontWeight: 500 }} onMouseEnter={(e) => { if (questionInput.trim()) e.currentTarget.style.backgroundColor = '#1D4ED8' }} onMouseLeave={(e) => { if (questionInput.trim()) e.currentTarget.style.backgroundColor = '#2563EB' }}>提交追问</button>
            </div>
          </div>
        </div>
      )}

      {profileModalOpen && (
        <div
          style={{
            position: 'fixed',
            top: 0, left: 0, right: 0, bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.5)',
            display: 'flex', justifyContent: 'center', alignItems: 'center', zIndex: 1000,
          }}
          onClick={() => setProfileModalOpen(false)}
        >
          <div
            style={{
              backgroundColor: 'white', borderRadius: '12px', padding: '24px',
              maxWidth: '820px', width: '92%', maxHeight: '80vh', overflowY: 'auto',
              boxShadow: '0 10px 25px rgba(0, 0, 0, 0.15)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h2 style={{ fontSize: '20px', fontWeight: 600, margin: 0, color: '#111827' }}>学习画像</h2>
              <button
                onClick={() => setProfileModalOpen(false)}
                style={{
                  padding: '4px 8px', border: 'none', backgroundColor: 'transparent',
                  cursor: 'pointer', fontSize: '20px', color: '#6B7280',
                }}
                onMouseEnter={(e) => { e.currentTarget.style.color = '#111827' }}
                onMouseLeave={(e) => { e.currentTarget.style.color = '#6B7280' }}
              >
                ×
              </button>
            </div>
            <div style={{ display: 'flex', gap: '24px', minHeight: '320px' }}>
              <div style={{ flex: 1, minWidth: 0, borderRight: '1px solid #E5E7EB', paddingRight: '24px' }}>
                <p style={{ fontSize: '14px', color: '#6B7280', margin: '0 0 12px 0' }}>正在学习的概念（拖到右侧或点击加入计划）</p>
                {profileLoading && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#6B7280', padding: '24px' }}>
                    <div style={{ width: '20px', height: '20px', border: '2px solid #E5E7EB', borderTopColor: '#2563EB', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
                    <span>加载中...</span>
                  </div>
                )}
                {!profileLoading && profileError && (
                  <div style={{ padding: '16px', color: '#DC2626', backgroundColor: '#FEF2F2', borderRadius: '8px' }}>{profileError}</div>
                )}
                {!profileLoading && !profileError && profileList.length === 0 && (
                  <div style={{ padding: '24px', textAlign: 'center', color: '#6B7280' }}>暂无学习记录</div>
                )}
                {!profileLoading && !profileError && profileList.length > 0 && (
                  <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
                    {profileList.map((item, i) => (
                      <li
                        key={item.concept + i}
                        draggable
                        onDragStart={(e) => {
                          e.dataTransfer.setData('text/plain', item.concept)
                          e.dataTransfer.effectAllowed = 'copy'
                        }}
                        style={{
                          padding: '10px 12px', border: '1px solid #E5E7EB', borderRadius: '8px', marginBottom: '6px',
                          display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px',
                          cursor: 'grab', backgroundColor: 'white',
                        }}
                      >
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <span style={{ fontWeight: 600, color: '#111827' }}>{item.concept}</span>
                          <div style={{ fontSize: '12px', color: '#6B7280' }}>
                            练习 {item.times} 次 · 得分 {(item.score * 100).toFixed(0)}%
                          </div>
                        </div>
                        <div style={{ display: 'flex', gap: '6px', flexShrink: 0 }}>
                          <button
                            type="button"
                            onClick={async () => {
                              if (planList.includes(item.concept)) return
                              try {
                                await profileAPI.addToPlan(item.concept)
                                setPlanList(prev => [...prev, item.concept])
                              } catch (e) {
                                setProfileError(e instanceof Error ? e.message : '加入计划失败')
                              }
                            }}
                            disabled={planList.includes(item.concept)}
                            style={{
                              padding: '4px 8px', border: '1px solid #86EFAC', borderRadius: '6px',
                              backgroundColor: planList.includes(item.concept) ? '#F0FDF4' : 'white', color: '#166534', cursor: planList.includes(item.concept) ? 'default' : 'pointer', fontSize: '12px',
                            }}
                          >
                            加入计划
                          </button>
                          <button
                            type="button"
                            onClick={async () => {
                              try {
                                await profileAPI.deleteConcept(item.concept)
                                setProfileList(prev => prev.filter(p => p.concept !== item.concept))
                                setPlanList(prev => prev.filter(c => c !== item.concept))
                              } catch (e) {
                                setProfileError(e instanceof Error ? e.message : '删除失败')
                              }
                            }}
                            style={{
                              padding: '4px 8px', border: '1px solid #D1D5DB', borderRadius: '6px',
                              backgroundColor: 'white', color: '#6B7280', cursor: 'pointer', fontSize: '12px',
                            }}
                            onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = '#FEF2F2'; e.currentTarget.style.color = '#DC2626' }}
                            onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'white'; e.currentTarget.style.color = '#6B7280' }}
                          >
                            删除
                          </button>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div
                style={{
                  flex: 1,
                  minWidth: 0,
                  border: '2px dashed #BBF7D0',
                  borderRadius: '12px',
                  padding: '12px',
                  backgroundColor: '#F0FDF4',
                }}
                onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'copy' }}
                onDrop={(e) => {
                  e.preventDefault()
                  const concept = e.dataTransfer.getData('text/plain')
                  if (!concept || planList.includes(concept)) return
                  profileAPI.addToPlan(concept).then(() => setPlanList(prev => [...prev, concept])).catch(() => setProfileError('加入计划失败'))
                }}
              >
                <p style={{ fontSize: '14px', color: '#166534', margin: '0 0 12px 0', fontWeight: 600 }}>学习计划</p>
                {planList.length === 0 ? (
                  <p style={{ fontSize: '13px', color: '#6B7280', margin: 0 }}>将左侧概念拖入此处，或点击「加入计划」</p>
                ) : (
                  <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
                    {planList.map((c, i) => (
                      <li
                        key={c + i}
                        style={{
                          padding: '8px 12px', border: '1px solid #86EFAC', borderRadius: '8px', marginBottom: '6px',
                          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                          backgroundColor: 'white',
                        }}
                      >
                        <span style={{ fontWeight: 500, color: '#111827' }}>{c}</span>
                        <button
                          type="button"
                          onClick={async () => {
                            try {
                              await profileAPI.removeFromPlan(c)
                              setPlanList(prev => prev.filter(x => x !== c))
                            } catch (e) {
                              setProfileError(e instanceof Error ? e.message : '移出失败')
                            }
                          }}
                          style={{
                            padding: '2px 8px', border: '1px solid #D1D5DB', borderRadius: '6px',
                            backgroundColor: 'white', color: '#6B7280', cursor: 'pointer', fontSize: '12px',
                          }}
                          onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = '#FEF2F2'; e.currentTarget.style.color = '#DC2626' }}
                          onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'white'; e.currentTarget.style.color = '#6B7280' }}
                        >
                          移出计划
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default ChatInterface
