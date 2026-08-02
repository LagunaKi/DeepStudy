/**
 * API 服务封装
 * 处理所有与后端的 HTTP 通信
 */
import axios, { AxiosInstance } from 'axios'
import {
  ChatRequest,
  AgentResponse,
  MindMapGraph,
  DialogueNodeBase,
  ConceptProfileSummary,
  ChatSessionDetail,
  ChatSessionSummary,
  AgentTraceEvent,
  AttachmentInfo,
  RAGDocument,
  RAGSource,
} from '../types/api'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api'

export interface ChatStreamEvent {
  type: string
  text?: string
  message?: string
  code?: 'rate_limit' | 'quota_exhausted' | 'model_error' | string
  retry_after?: number
  conversation_id?: string
  parent_id?: string
  answer?: string
  runtime?: string
  node?: AgentTraceEvent['node']
  status?: AgentTraceEvent['status']
  title?: string
  summary?: string
  details?: Record<string, unknown>
  timestamp?: string
  items?: RAGSource[]
}

export const knowledgeAPI = {
  upload: async (
    sessionId: string,
    file: File,
  ): Promise<{ attachment: AttachmentInfo; document: RAGDocument | null; deduplicated: boolean }> => {
    const body = new FormData()
    body.append('session_id', sessionId)
    body.append('file', file)
    const response = await fetch(`${API_BASE_URL}/knowledge/upload`, { method: 'POST', body })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(payload.detail || `上传失败: ${response.status}`)
    return payload
  },

  getDocument: async (documentId: string): Promise<RAGDocument> => {
    const response = await apiClient.get<RAGDocument>(`/knowledge/documents/${documentId}`)
    return response.data
  },

  listDocuments: async (sessionId: string): Promise<RAGDocument[]> => {
    const response = await apiClient.get<RAGDocument[]>('/knowledge/documents', {
      params: { session_id: sessionId },
    })
    return response.data
  },

  sourceUrl: (source: RAGSource): string => {
    const page = source.page ? `#page=${source.page}` : ''
    return `${API_BASE_URL}/knowledge/documents/${source.document_id}/content${page}`
  },

  getGraph: async (sessionId: string): Promise<MindMapGraph> => {
    const response = await apiClient.get<MindMapGraph>('/knowledge/graph', {
      params: { session_id: sessionId },
    })
    return response.data
  },
}

/**
 * 创建 axios 实例
 */
const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

/**
 * 聊天 API
 */
export const chatAPI = {
  /**
   * 发送聊天消息（支持普通提问和划词追问）
   */
  sendMessage: async (data: ChatRequest): Promise<AgentResponse> => {
    const response = await apiClient.post<AgentResponse>('/chat', data)
    return response.data
  },

  /**
   * 发送聊天消息（流式接口）
   * 使用 fetch + ReadableStream 消费后端 StreamingResponse
   */
  sendMessageStream: async (
    data: ChatRequest,
    onChunk: (payload: ChatStreamEvent) => void
  ): Promise<void> => {
    const response = await fetch(`${API_BASE_URL}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
    })

    if (!response.ok) {
      throw new Error(`请求失败: ${response.status}`)
    }

    if (!response.body) {
      throw new Error('后端未返回流数据')
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''

    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      let index: number
      // SSE 事件以空行分隔；data 字段内承载 JSON。
      while ((index = buffer.indexOf('\n\n')) >= 0) {
        const block = buffer.slice(0, index).trim()
        buffer = buffer.slice(index + 2)
        if (!block) continue
        try {
          const data = block
            .split('\n')
            .filter((line) => line.startsWith('data:'))
            .map((line) => line.slice(5).trimStart())
            .join('\n')
          if (!data) continue
          const payload = JSON.parse(data)
          onChunk(payload)
        } catch (e) {
          console.warn('解析 SSE 事件失败:', e, block)
        }
      }
    }

    // 处理最后残留的 buffer
    const rest = buffer.trim().replace(/^data:\s*/, '')
    if (rest) {
      try {
        const payload = JSON.parse(rest)
        onChunk(payload)
      } catch (e) {
        console.warn('解析流式数据失败(尾部):', e, rest)
      }
    }
  },

  /**
   * 获取对话树
   */
  getConversationTree: async (conversationId: string): Promise<DialogueNodeBase> => {
    const response = await apiClient.get<DialogueNodeBase>(
      `/chat/conversation/${conversationId}`
    )
    return response.data
  },
}

export const sessionAPI = {
  list: async (): Promise<ChatSessionSummary[]> => {
    const response = await apiClient.get<ChatSessionSummary[]>('/sessions')
    return response.data
  },

  create: async (title = '新对话'): Promise<ChatSessionSummary> => {
    const response = await apiClient.post<ChatSessionSummary>('/sessions', { title })
    return response.data
  },

  get: async (sessionId: string): Promise<ChatSessionDetail> => {
    const response = await apiClient.get<ChatSessionDetail>(`/sessions/${sessionId}`)
    return response.data
  },

  rename: async (sessionId: string, title: string): Promise<void> => {
    await apiClient.patch(`/sessions/${sessionId}`, { title })
  },

  remove: async (sessionId: string): Promise<void> => {
    await apiClient.delete(`/sessions/${sessionId}`)
  },
}

/**
 * 知识图谱 API
 */
export const mindMapAPI = {
  /**
   * 获取思维导图数据
   */
  getMindMap: async (conversationId: string): Promise<MindMapGraph> => {
    const response = await apiClient.get<MindMapGraph>(
      `/mindmap/${conversationId}`
    )
    return response.data
  },
}

/**
 * 学习画像 API
 */
export const profileAPI = {
  /**
   * 获取当前用户的概念画像摘要列表（正在学习的概念）
   */
  getSummary: async (): Promise<ConceptProfileSummary[]> => {
    const response = await apiClient.get<ConceptProfileSummary[]>('/profile/summary')
    return response.data
  },

  /**
   * 从学习画像中删除指定概念（仅删画像行，保留追溯）
   */
  deleteConcept: async (concept: string): Promise<void> => {
    await apiClient.delete('/profile/concepts', { data: { concept } })
  },

  /**
   * 获取学习计划（概念名列表）
   */
  getPlan: async (): Promise<string[]> => {
    const response = await apiClient.get<string[]>('/profile/plan')
    return response.data
  },

  /**
   * 将概念加入学习计划
   */
  addToPlan: async (concept: string): Promise<void> => {
    await apiClient.post('/profile/plan', { concept })
  },

  /**
   * 从学习计划中移除概念
   */
  removeFromPlan: async (concept: string): Promise<void> => {
    await apiClient.delete('/profile/plan', { data: { concept } })
  },
}
