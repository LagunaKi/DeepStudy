import { useState, useEffect, useRef, useCallback } from 'react'
import axios from 'axios'
import {
  ChatStreamEvent,
  chatAPI,
  knowledgeAPI,
  mindMapAPI,
  profileAPI,
  sessionAPI,
} from '../../services/api'
import {
  AgentResponse,
  AgentTraceEvent,
  AttachmentInfo,
  ChatSessionDetail,
  ChatSessionSummary,
  ConceptProfileSummary,
  MindMapEdge,
  MindMapGraph,
  MindMapNode,
} from '../../types/api'
import TextFragment from '../Markdown/TextFragment'
import KnowledgeGraph from '../MindMap/KnowledgeGraph'
import ConversationSidebar from './ConversationSidebar'
import AgentTrace from './AgentTrace'
import MemoryCenter from '../Memory/MemoryCenter'

interface ChatTurn {
  id: string
  user: string
  assistant: AgentResponse
  status: 'loading' | 'complete' | 'error'
  trace: AgentTraceEvent[]
  attachments: AttachmentInfo[]
}

const emptyAssistant = (parentId: string | null = null): AgentResponse => ({
  answer: '',
  fragments: [],
  knowledge_triples: [],
  suggestion: undefined,
  conversation_id: '',
  parent_id: parentId,
  sources: [],
})

const detailToTurns = (detail: ChatSessionDetail): ChatTurn[] => {
  const turns: ChatTurn[] = []
  detail.messages.forEach((message) => {
    if (message.role === 'user') {
      turns.push({
        id: message.id,
        user: message.content,
        assistant: emptyAssistant(message.parent_id || null),
        status: 'complete',
        trace: [],
        attachments: message.attachments || [],
      })
      return
    }

    const target = turns[turns.length - 1]
    if (!target) return
    target.assistant = {
      ...emptyAssistant(message.parent_id || null),
      answer: message.status === 'error' ? '' : message.content,
      conversation_id: message.conversation_id || '',
      sources: message.sources || [],
    }
    target.status = message.status === 'error' ? 'error' : 'complete'
    target.trace = message.agent_trace || []
  })
  return turns
}

const ChatInterface = () => {
  // --- 基础 Refs ---
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  
  // --- 基础 State ---
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [input, setInput] = useState<string>('')
  const [loading, setLoading] = useState<boolean>(false)
  const [hasFirstChunk, setHasFirstChunk] = useState<boolean>(false)
  const [error, setError] = useState<string>('')
  const [cooldownSeconds, setCooldownSeconds] = useState(0)
  const [quotaExhausted, setQuotaExhausted] = useState(false)
  
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(true)
  const [mapView, setMapView] = useState<'mindmap' | 'graph'>('mindmap')
  const [sidebarWidth, setSidebarWidth] = useState<number>(400)
  const [isResizing, setIsResizing] = useState<boolean>(false)
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([])
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [sessionsLoading, setSessionsLoading] = useState(true)
  const [pendingAttachments, setPendingAttachments] = useState<AttachmentInfo[]>([])
  const [uploading, setUploading] = useState(false)
  
  const [questionModalOpen, setQuestionModalOpen] = useState(false)
  const [selectedFragmentId, setSelectedFragmentId] = useState<string>('')
  const [selectedText, setSelectedText] = useState<string>('')
  const [questionInput, setQuestionInput] = useState<string>('')

  const [profileModalOpen, setProfileModalOpen] = useState(false)
  const [memoryCenterOpen, setMemoryCenterOpen] = useState(false)
  const [profileList, setProfileList] = useState<ConceptProfileSummary[]>([])
  const [profileLoading, setProfileLoading] = useState(false)
  const [profileError, setProfileError] = useState<string>('')
  const [planList, setPlanList] = useState<string[]>([])

  // ⭐⭐⭐ 核心 State ⭐⭐⭐
  // 1. mindMapData: 最终展示给用户的完整大图
  const [mindMapData, setMindMapData] = useState<MindMapGraph>({ nodes: [], edges: [] })
  const [domainGraphData, setDomainGraphData] = useState<MindMapGraph>({ nodes: [], edges: [] })
  
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

  useEffect(() => {
    if (mapView !== 'graph' || !activeSessionId || !sidebarOpen) return
    let mounted = true
    const refresh = () => {
      knowledgeAPI.getGraph(activeSessionId).then((data) => {
        if (mounted) setDomainGraphData(data)
      }).catch(() => {})
    }
    refresh()
    const timer = window.setInterval(refresh, 3000)
    return () => {
      mounted = false
      window.clearInterval(timer)
    }
  }, [activeSessionId, mapView, sidebarOpen])

  // ==========================================

  const refreshSessions = useCallback(async () => {
    const nextSessions = await sessionAPI.list()
    setSessions(nextSessions)
    return nextSessions
  }, [])

  const handleSelectSession = useCallback(async (sessionId: string) => {
    if (loading || sessionId === activeSessionId) return
    setSessionsLoading(true)
    setError('')
    try {
      const detail = await sessionAPI.get(sessionId)
      const loadedTurns = detailToTurns(detail)
      setActiveSessionId(sessionId)
      setTurns(loadedTurns)
      setPendingAttachments([])
      setMindMapData({ nodes: [], edges: [] })
      setDomainGraphData({ nodes: [], edges: [] })
      const latestConversationId = [...loadedTurns]
        .reverse()
        .find((turn) => turn.assistant.conversation_id)?.assistant.conversation_id
      setCurrentPollingId(latestConversationId || null)
    } catch (sessionError) {
      console.error('加载会话失败:', sessionError)
      setError('历史会话加载失败，请重试')
    } finally {
      setSessionsLoading(false)
    }
  }, [activeSessionId, loading])

  const handleCreateSession = useCallback(async () => {
    if (loading) return
    setSessionsLoading(true)
    setError('')
    try {
      const created = await sessionAPI.create()
      setSessions((previous) => [created, ...previous])
      setActiveSessionId(created.id)
      setTurns([])
      setPendingAttachments([])
      setMindMapData({ nodes: [], edges: [] })
      setDomainGraphData({ nodes: [], edges: [] })
      setCurrentPollingId(null)
      requestAnimationFrame(() => inputRef.current?.focus())
    } catch (sessionError) {
      console.error('新建会话失败:', sessionError)
      setError('新建会话失败，请确认后端已启动')
    } finally {
      setSessionsLoading(false)
    }
  }, [loading])

  const handleRenameSession = useCallback(async (session: ChatSessionSummary) => {
    const title = window.prompt('输入新的会话标题', session.title)?.trim()
    if (!title || title === session.title) return
    try {
      await sessionAPI.rename(session.id, title)
      setSessions((previous) => previous.map((item) => (
        item.id === session.id ? { ...item, title } : item
      )))
    } catch (sessionError) {
      console.error('重命名会话失败:', sessionError)
      setError('重命名会话失败，请重试')
    }
  }, [])

  const handleDeleteSession = useCallback(async (session: ChatSessionSummary) => {
    if (!window.confirm(`删除会话“${session.title}”？此操作会删除该会话的本地消息历史。`)) {
      return
    }
    try {
      await sessionAPI.remove(session.id)
      const remaining = sessions.filter((item) => item.id !== session.id)
      setSessions(remaining)
      if (activeSessionId !== session.id) return

      if (remaining.length > 0) {
        setActiveSessionId(null)
        await handleSelectSession(remaining[0].id)
      } else {
        setActiveSessionId(null)
        setTurns([])
        const created = await sessionAPI.create()
        setSessions([created])
        setActiveSessionId(created.id)
      }
    } catch (sessionError) {
      console.error('删除会话失败:', sessionError)
      setError('删除会话失败，请重试')
    }
  }, [activeSessionId, handleSelectSession, sessions])

  useEffect(() => {
    let mounted = true
    const bootstrapSessions = async () => {
      setSessionsLoading(true)
      try {
        let existing = await sessionAPI.list()
        if (!mounted) return
        if (existing.length === 0) {
          const created = await sessionAPI.create()
          existing = [created]
        }
        if (!mounted) return
        setSessions(existing)
        const detail = await sessionAPI.get(existing[0].id)
        if (!mounted) return
        const loadedTurns = detailToTurns(detail)
        setActiveSessionId(existing[0].id)
        setTurns(loadedTurns)
        const latestConversationId = [...loadedTurns]
          .reverse()
          .find((turn) => turn.assistant.conversation_id)?.assistant.conversation_id
        setCurrentPollingId(latestConversationId || null)
      } catch (sessionError) {
        console.error('初始化会话失败:', sessionError)
        if (mounted) setError('无法加载会话历史，请确认后端已启动')
      } finally {
        if (mounted) setSessionsLoading(false)
      }
    }
    bootstrapSessions()
    return () => {
      mounted = false
    }
  }, [])

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
  }, [turns.length, loading, hasFirstChunk])

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
  }, [turns, loading, hasFirstChunk])

  const pollDocument = useCallback(async (documentId: string, attachmentId: string) => {
    for (let attempt = 0; attempt < 90; attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 1000))
      const document = await knowledgeAPI.getDocument(documentId)
      setPendingAttachments((previous) => previous.map((attachment) => (
        attachment.id === attachmentId
          ? { ...attachment, status: document.status, progress: document.progress, error: document.error }
          : attachment
      )))
      if (document.status === 'ready') return
      if (document.status === 'failed') {
        setError(`${document.filename} 解析失败：${document.error || '未知原因'}`)
        return
      }
    }
    setError('文档处理时间较长，可稍后在当前会话继续提问')
  }, [])

  const uploadFiles = useCallback(async (files: File[]) => {
    if (!files.length || uploading) return
    let sessionId = activeSessionId
    setUploading(true)
    setError('')
    try {
      if (!sessionId) {
        const created = await sessionAPI.create()
        sessionId = created.id
        setSessions((previous) => [created, ...previous])
        setActiveSessionId(created.id)
      }
      const availableSlots = Math.max(0, 8 - pendingAttachments.length)
      if (availableSlots === 0) {
        setError('每轮最多添加 8 个附件')
        return
      }
      for (const file of files.slice(0, availableSlots)) {
        const result = await knowledgeAPI.upload(sessionId, file)
        setPendingAttachments((previous) => [...previous, result.attachment])
        if (result.document && !['ready', 'failed'].includes(result.document.status)) {
          void pollDocument(result.document.id, result.attachment.id)
        }
      }
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : '附件上传失败')
    } finally {
      setUploading(false)
    }
  }, [activeSessionId, pendingAttachments.length, pollDocument, uploading])

  const handleFileUpload = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || [])
    event.target.value = ''
    void uploadFiles(files)
  }, [uploadFiles])

  const handlePaste = useCallback((event: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const pastedImages = Array.from(event.clipboardData.items)
      .filter((item) => item.kind === 'file' && item.type.startsWith('image/'))
      .map((item, index) => {
        const image = item.getAsFile()
        if (!image) return null
        const subtype = image.type.split('/')[1]?.replace('jpeg', 'jpg') || 'png'
        const filename = image.name && image.name !== 'image.png'
          ? image.name
          : `clipboard-${Date.now()}-${index + 1}.${subtype}`
        return new File([image], filename, { type: image.type, lastModified: Date.now() })
      })
      .filter((file): file is File => file !== null)

    if (!pastedImages.length) return
    event.preventDefault()
    if (loading || uploading) {
      setError('请等待当前操作完成后再粘贴图片')
      return
    }
    void uploadFiles(pastedImages)
  }, [loading, uploadFiles, uploading])

  const handleSend = async (refFragmentId?: string, selectedText?: string, queryOverride?: string) => {
    const typedQuery = (queryOverride || input).trim()
    const hasImage = pendingAttachments.some(
      (attachment) => attachment.status === 'ready' && attachment.mime_type.startsWith('image/')
    )
    const query = typedQuery || (
      hasImage
        ? '请分析这张图片。'
        : pendingAttachments.length > 0
          ? '请总结这份资料的核心内容。'
          : ''
    )
    if (!query || loading) return
    if (cooldownSeconds > 0 || quotaExhausted) return
    if (pendingAttachments.some((attachment) => attachment.status !== 'ready')) {
      setError('请等待附件解析完成，或移除失败的附件后再发送')
      return
    }

    let sessionId = activeSessionId
    if (!sessionId) {
      try {
        const created = await sessionAPI.create()
        sessionId = created.id
        setSessions((previous) => [created, ...previous])
        setActiveSessionId(created.id)
      } catch (sessionError) {
        console.error('创建会话失败:', sessionError)
        setError('无法创建会话，请确认后端已启动')
        return
      }
    }

    if (!queryOverride) setInput('')
    setError('')
    setLoading(true)
    setHasFirstChunk(false)

    const parentId = [...turns]
      .reverse()
      .find((turn) => turn.assistant.conversation_id)?.assistant.conversation_id || null
    const turnId = crypto.randomUUID()
    const turnAttachments = [...pendingAttachments]
    setTurns((previous) => [
      ...previous,
      {
        id: turnId,
        user: query,
        assistant: emptyAssistant(parentId),
        status: 'loading',
        trace: [],
        attachments: turnAttachments,
      },
    ])

    const updateTurn = (updater: (turn: ChatTurn) => ChatTurn) => {
      setTurns((previous) => previous.map((turn) => (
        turn.id === turnId ? updater(turn) : turn
      )))
    }

    let streamFailed = false
    try {
      await chatAPI.sendMessageStream(
        {
          query,
          parent_id: parentId,
          ref_fragment_id: refFragmentId || null,
          selected_text: selectedText || null,
          session_id: sessionId,
          attachment_ids: turnAttachments.map((attachment) => attachment.id),
        },
        (payload: ChatStreamEvent) => {
          
          if (payload.conversation_id) {
            // ⭐ 核心逻辑：只要有了新 ID，就立刻把它设为当前轮询目标
            // 剩下的交给 useEffect 去把它抓回来并合并
            setCurrentPollingId(payload.conversation_id as string);
            
            if (!sidebarOpen) setSidebarOpen(true);
          }

          if (payload.type === 'meta' && payload.conversation_id) {
            updateTurn((turn) => ({
              ...turn,
              assistant: {
                ...turn.assistant,
                conversation_id: payload.conversation_id as string,
              },
            }))
          } else if (payload.type === 'agent' && payload.node && payload.status && payload.title && payload.summary) {
            const event = payload as AgentTraceEvent
            updateTurn((turn) => ({ ...turn, trace: [...turn.trace, event] }))
          } else if (payload.type === 'sources' && payload.items) {
            updateTurn((turn) => ({
              ...turn,
              assistant: { ...turn.assistant, sources: payload.items },
            }))
          } else if (payload.type === 'delta' && payload.text) {
            setHasFirstChunk(true)
            updateTurn((turn) => ({
              ...turn,
              assistant: {
                ...turn.assistant,
                answer: `${turn.assistant.answer || ''}${payload.text}`,
              },
            }))
          } else if (payload.type === 'full' && payload.answer) {
            updateTurn((turn) => ({
              ...turn,
              assistant: {
                ...emptyAssistant(payload.parent_id || null),
                answer: payload.answer as string,
                conversation_id: payload.conversation_id || turn.assistant.conversation_id,
              },
            }))
          } else if (payload.type === 'error') {
            streamFailed = true
            updateTurn((turn) => ({ ...turn, status: 'error' }))
            if (payload.code === 'quota_exhausted') {
              setQuotaExhausted(true)
              setCooldownSeconds(0)
              setError('')
            } else if (payload.code === 'rate_limit') {
              setCooldownSeconds(Math.max(1, Math.ceil(payload.retry_after || 60)))
              setError('')
            } else {
              setError(payload.message || '模型生成失败，请重试')
            }
          }
        }
      )
      updateTurn((turn) => ({ ...turn, status: turn.status === 'error' ? 'error' : 'complete' }))
      if (!streamFailed) setPendingAttachments([])
    } catch (error: unknown) {
      console.error('发送消息失败:', error)
      updateTurn((turn) => ({ ...turn, status: 'error' }))
      if (axios.isAxiosError(error) && error.response?.status === 404) {
        setError('聊天功能暂时不可用，请稍后再试')
      } else {
        setError(error instanceof Error ? error.message : '发送消息失败，请稍后再试')
      }
    } finally {
      setLoading(false)
      refreshSessions().catch(() => {})
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

  useEffect(() => {
    if (cooldownSeconds <= 0) return
    const timer = window.setTimeout(() => {
      setCooldownSeconds((seconds) => Math.max(0, seconds - 1))
    }, 1000)
    return () => window.clearTimeout(timer)
  }, [cooldownSeconds])

  const handleQuestionSubmit = async () => {
    if (!questionInput.trim()) return
    if (cooldownSeconds > 0 || quotaExhausted) return
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
    cursor: loading || cooldownSeconds > 0 || quotaExhausted || !input.trim() ? 'not-allowed' : 'pointer',
    opacity: loading || cooldownSeconds > 0 || quotaExhausted || !input.trim() ? 0.6 : 1,
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
  const sendDisabled = (
    loading
    || cooldownSeconds > 0
    || quotaExhausted
    || uploading
    || pendingAttachments.some((attachment) => attachment.status !== 'ready')
    || (!input.trim() && pendingAttachments.length === 0)
  )

  return (
    <div style={containerStyle} ref={containerRef}>
      <div style={backgroundStyle} />
      <ConversationSidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        loading={sessionsLoading || loading}
        onCreate={handleCreateSession}
        onSelect={handleSelectSession}
        onRename={handleRenameSession}
        onDelete={handleDeleteSession}
      />
      <div style={mainAreaStyle}>
        <div style={headerStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div>
              <h1 style={{ fontSize: '17px', fontWeight: 650, color: '#111827', margin: 0 }}>
                {sessions.find((session) => session.id === activeSessionId)?.title || '新对话'}
              </h1>
              <span style={{ fontSize: '11px', color: '#6B7280' }}>
                递归学习 · 会话内容自动保存
              </span>
            </div>
          </div>
          <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
            <button
              onClick={() => setMemoryCenterOpen(true)}
              style={{
                padding: '8px 16px', border: '1px solid #C4B5FD', borderRadius: '6px',
                backgroundColor: '#F5F3FF', cursor: 'pointer', fontSize: '14px', color: '#5B21B6',
              }}
            >
              记忆中心
            </button>
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
              {sidebarOpen ? '隐藏学习地图' : '显示学习地图'}
            </button>
          </div>
        </div>

        <div style={messagesAreaStyle} ref={scrollContainerRef}>
          {turns.length === 0 && (
            <div style={{ textAlign: 'center', color: '#6B7280', marginTop: '100px' }}>
              <h2 style={{ fontSize: '24px', marginBottom: '8px', color: '#111827' }}>
                开始你的学习之旅
              </h2>
              <p>输入你的问题，AI 助手会帮助你深入理解</p>
            </div>
          )}
          {turns.map((turn, index) => (
            <div key={turn.id}>
              <div style={userMessageStyle}>
                <div style={userBubbleStyle}>
                  {turn.user}
                  {turn.attachments.length > 0 && (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '8px' }}>
                      {turn.attachments.map((attachment) => (
                        <span
                          key={attachment.id}
                          style={{ fontSize: '11px', padding: '3px 7px', borderRadius: '999px', background: 'rgba(255,255,255,.18)' }}
                        >
                          📎 {attachment.filename}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
              <div style={aiMessageStyle}>
                <div style={aiCardStyle}>
                  <AgentTrace
                    events={turn.trace}
                    active={turn.status === 'loading' && loading && index === turns.length - 1}
                  />
                  {turn.assistant.answer ? (
                    <>
                      <TextFragment
                        content={turn.assistant.answer}
                        fragments={turn.assistant.fragments || []}
                        onFragmentSelect={handleFragmentSelect}
                      />
                      {(turn.assistant.sources || []).length > 0 && (
                        <div style={{ marginTop: '16px', paddingTop: '12px', borderTop: '1px solid #E5E7EB' }}>
                          <div style={{ fontSize: '12px', fontWeight: 650, color: '#374151', marginBottom: '8px' }}>
                            来源
                          </div>
                          <div style={{ display: 'grid', gap: '7px' }}>
                            {(turn.assistant.sources || []).map((source) => (
                              <a
                                key={source.chunk_id}
                                href={knowledgeAPI.sourceUrl(source)}
                                target="_blank"
                                rel="noreferrer"
                                style={{ color: '#1D4ED8', fontSize: '12px', textDecoration: 'none' }}
                                title={source.snippet}
                              >
                                [{source.citation}] {source.filename}
                                {source.page ? ` · 第 ${source.page} 页` : ''}
                                {source.section ? ` · ${source.section}` : ''}
                              </a>
                            ))}
                          </div>
                        </div>
                      )}
                    </>
                    ) : turn.status === 'loading' && loading && !hasFirstChunk && index === turns.length - 1 ? (
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
                    ) : turn.status === 'error' ? (
                      <div style={{ color: '#B91C1C', fontSize: '14px' }}>
                        本轮回答失败。
                        <button
                          onClick={() => handleSend(undefined, undefined, turn.user)}
                          disabled={cooldownSeconds > 0 || quotaExhausted}
                          style={{
                            marginLeft: '8px',
                            border: 0,
                            color: cooldownSeconds > 0 || quotaExhausted ? '#9CA3AF' : '#2563EB',
                            background: 'none',
                            cursor: cooldownSeconds > 0 || quotaExhausted ? 'not-allowed' : 'pointer',
                          }}
                        >
                          {quotaExhausted
                            ? '今日额度已用完'
                            : cooldownSeconds > 0
                              ? `${cooldownSeconds} 秒后重试`
                              : '重试'}
                        </button>
                      </div>
                    ) : null}
                </div>
              </div>
            </div>
          ))}
          {quotaExhausted && (
            <div
              style={{
                ...errorStyle,
                backgroundColor: '#FFF7ED',
                color: '#C2410C',
                border: '1px solid #FED7AA',
              }}
              role="alert"
            >
              Gemini 3 Flash 今日免费请求额度已用完。代码无法绕过服务商的每日上限，
              请等待 Google 配额重置后刷新页面再试。
            </div>
          )}
          {cooldownSeconds > 0 && (
            <div
              style={{
                ...errorStyle,
                backgroundColor: '#FFF7ED',
                color: '#C2410C',
                border: '1px solid #FED7AA',
              }}
              role="alert"
            >
              Gemini 免费额度正在冷却，请等待 {cooldownSeconds} 秒后重试。系统不会在此期间继续消耗请求。
            </div>
          )}
          {error && <div style={errorStyle} role="alert">{error}</div>}
          <div ref={messagesEndRef} />
        </div>

        {pendingAttachments.length > 0 && (
          <div style={{ padding: '10px 24px 0', borderTop: '1px solid #E5E7EB', background: 'white', display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            {pendingAttachments.map((attachment) => (
              <div key={attachment.id} style={{ display: 'flex', alignItems: 'center', gap: '7px', padding: '7px 9px', border: '1px solid #D1D5DB', borderRadius: '8px', fontSize: '12px' }}>
                <span>{attachment.mime_type.startsWith('image/') ? '🖼️' : '📎'} {attachment.filename}</span>
                <span style={{ color: attachment.status === 'failed' ? '#B91C1C' : '#6B7280' }}>
                  {attachment.status === 'ready' ? '可用' : attachment.status === 'failed' ? '失败' : `${attachment.progress}%`}
                </span>
                <button
                  type="button"
                  aria-label={`移除 ${attachment.filename}`}
                  onClick={() => setPendingAttachments((previous) => previous.filter((item) => item.id !== attachment.id))}
                  style={{ border: 0, background: 'none', cursor: 'pointer', color: '#6B7280' }}
                >×</button>
              </div>
            ))}
          </div>
        )}
        <div style={{ ...inputAreaStyle, borderTop: pendingAttachments.length ? 'none' : inputAreaStyle.borderTop }}>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".pdf,.md,.markdown,.txt,.py,.js,.jsx,.ts,.tsx,.java,.c,.cpp,.h,.hpp,.go,.rs,.sql,.json,.yaml,.yml,.html,.css,.scss,.sh,.png,.jpg,.jpeg,.webp,.gif"
            onChange={handleFileUpload}
            style={{ display: 'none' }}
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={loading || uploading}
            title="上传课程资料或图片"
            style={{ padding: '11px 13px', border: '1px solid #D1D5DB', borderRadius: '8px', background: 'white', cursor: loading || uploading ? 'not-allowed' : 'pointer' }}
          >
            {uploading ? '上传中…' : '📎'}
          </button>
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => {
              setInput(e.target.value)
              setError('')
            }}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            placeholder="输入问题或直接粘贴图片… (Enter 发送)"
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
            disabled={sendDisabled}
            style={{ ...buttonStyle, cursor: sendDisabled ? 'not-allowed' : 'pointer', opacity: sendDisabled ? 0.6 : 1 }}
            onMouseEnter={(e) => {
              if (!sendDisabled) {
                e.currentTarget.style.backgroundColor = '#1D4ED8'
              }
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = '#2563EB'
            }}
          >
            {loading
              ? '发送中...'
              : quotaExhausted
                ? '今日额度已用完'
                : cooldownSeconds > 0
                  ? `${cooldownSeconds}s`
                  : '发送'}
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
            <div>
              <h3 style={{ fontSize: '18px', fontWeight: 600, margin: 0, color: '#111827' }}>
                {mapView === 'mindmap' ? '学习思维导图' : '知识关系图'}
              </h3>
              <div style={{ display: 'flex', gap: '4px', marginTop: '8px' }}>
                {(['mindmap', 'graph'] as const).map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => setMapView(mode)}
                    style={{
                      padding: '4px 8px',
                      border: '1px solid #D1D5DB',
                      borderRadius: '6px',
                      background: mapView === mode ? '#DBEAFE' : 'white',
                      color: mapView === mode ? '#1D4ED8' : '#64748B',
                      cursor: 'pointer',
                      fontSize: '11px',
                    }}
                  >
                    {mode === 'mindmap' ? '思维导图' : '关系图'}
                  </button>
                ))}
              </div>
            </div>
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
            <KnowledgeGraph
              data={mapView === 'mindmap' ? mindMapData : domainGraphData}
              planConcepts={planList}
              viewMode={mapView}
            />
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
      <MemoryCenter open={memoryCenterOpen} onClose={() => setMemoryCenterOpen(false)} />
    </div>
  )
}

export default ChatInterface
