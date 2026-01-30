/**
 * API 请求和响应的 TypeScript 类型定义
 */

/**
 * 用户注册请求
 */
export interface UserCreate {
  username: string
  email: string
  password: string
}

/**
 * 用户登录请求
 */
export interface UserLogin {
  username: string
  password: string
}

/**
 * 认证响应
 */
export interface AuthResponse {
  access_token: string
  token_type: string
  user_id: string
  username: string
}

/**
 * 前端请求格式：划词追问时发送的数据
 */
export interface ChatRequest {
  query: string
  parent_id?: string | null // 当前所在节点的 ID，首次提问可为空
  ref_fragment_id?: string | null // 如果是划词追问，需带上片段 ID
  session_id: string // 会话 ID，区分不同学习主题
}

/**
 * 片段模型：用于划词引用的核心单元
 */
export interface ContentFragment {
  id: string // 对应 HTML 中的 <span id="frag_xxx">
  type: 'text' | 'formula' | 'code' | 'concept'
  content: string // 具体内容
}

/**
 * 知识图谱三元组：支撑 Chat-to-Graph
 */
export interface KnowledgeTriple {
  subject: string
  relation: string
  object: string
}

/**
 * Agent 层输出协议
 */
export interface AgentResponse {
  answer: string // 包含 <span id="..."> 标签的 Markdown 回答
  fragments: ContentFragment[] // 提取出的所有知识点
  knowledge_triples: KnowledgeTriple[] // 知识图谱三元组：支撑 Chat-to-Graph
  suggestion?: string // 诊断建议，例如："建议复习特征值相关概念"
  conversation_id: string
  parent_id?: string | null
}

/**
 * UI层状态协议：兼容 ReactFlow 的节点格式
 */
export interface MindMapGraph {
  nodes: Array<{
    id: string
    data: {
      label: string
      mastery?: number // 掌握度评分 (0-1)
      [key: string]: any
    }
    position: { x: number; y: number }
    [key: string]: any
  }>
  edges: Array<{
    id: string
    source: string
    target: string
    label?: string
    [key: string]: any
  }>
}

/**
 * 对话节点模型：树状结构的基础
 */
export interface DialogueNodeBase {
  node_id: string // 全局唯一ID
  parent_id?: string | null // 溯源关键：指向父节点 ID
  user_id: string // 所属用户ID，确保数据隔离
  role: 'user' | 'assistant' // 角色
  content: string // 原始 Markdown 文本
  intent?: 'derivation' | 'code' | 'concept' // 意图识别
  mastery_score: number // 掌握度评分 (0-1)
  timestamp: string
  children: DialogueNodeBase[] // 子节点列表
}

// 为了向后兼容，保留 ConversationNode 作为别名
export type ConversationNode = DialogueNodeBase

/**
 * 错误响应
 */
export interface ErrorResponse {
  status: string
  code: number
  message: string
  detail?: string
}
