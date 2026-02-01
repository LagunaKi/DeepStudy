/**
 * ReactFlow 相关类型扩展
 */
import { Node, Edge } from 'reactflow'
import { MindMapGraph } from './api'

/**
 * 从 MindMapGraph 中提取节点和边的类型
 */
type MindMapNode = MindMapGraph['nodes'][number]

/**
 * 扩展的 ReactFlow Node 类型
 */
export type KnowledgeNode = Node<MindMapNode['data']>

/**
 * 扩展的 ReactFlow Edge 类型
 */
export type KnowledgeEdge = Edge

/**
 * 知识图谱数据
 */
export interface KnowledgeGraphData {
  nodes: KnowledgeNode[]
  edges: KnowledgeEdge[]
}
