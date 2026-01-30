/**
 * API 服务封装
 * 处理所有与后端的 HTTP 通信，包括 JWT token 管理
 */
import axios, { AxiosInstance, AxiosError } from 'axios'
import {
  UserCreate,
  UserLogin,
  AuthResponse,
  ChatRequest,
  AgentResponse,
  MindMapGraph,
  DialogueNodeBase,
  ErrorResponse,
} from '../types/api'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api'

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
 * 请求拦截器：添加 JWT token
 */
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

/**
 * 响应拦截器：处理 token 过期
 */
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ErrorResponse>) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

/**
 * 认证 API
 */
export const authAPI = {
  /**
   * 用户注册
   */
  register: async (data: UserCreate): Promise<AuthResponse> => {
    const response = await apiClient.post<AuthResponse>('/auth/register', data)
    if (response.data.access_token) {
      localStorage.setItem('access_token', response.data.access_token)
    }
    return response.data
  },

  /**
   * 用户登录
   */
  login: async (data: UserLogin): Promise<AuthResponse> => {
    const response = await apiClient.post<AuthResponse>('/auth/login', data)
    if (response.data.access_token) {
      localStorage.setItem('access_token', response.data.access_token)
    }
    return response.data
  },

  /**
   * 用户登出
   */
  logout: (): void => {
    localStorage.removeItem('access_token')
  },
}

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
    onChunk: (payload: { type: string; text?: string; conversation_id?: string; parent_id?: string }) => void
  ): Promise<void> => {
    const token = localStorage.getItem('access_token')
    const response = await fetch(`${API_BASE_URL}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(data),
    })

    if (!response.body) {
      throw new Error('后端未返回流数据')
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      let index: number
      // 按行拆分 JSON（后端以 \\n 作为分隔符）
      while ((index = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, index).trim()
        buffer = buffer.slice(index + 1)
        if (!line) continue
        try {
          const payload = JSON.parse(line)
          onChunk(payload)
        } catch (e) {
          // 忽略单行解析错误，避免中断整个流
          // eslint-disable-next-line no-console
          console.warn('解析流式数据失败:', e, line)
        }
      }
    }

    // 处理最后残留的 buffer
    const rest = buffer.trim()
    if (rest) {
      try {
        const payload = JSON.parse(rest)
        onChunk(payload)
      } catch (e) {
        // eslint-disable-next-line no-console
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
