/**
 * ReactFlow 相关类型扩展
 */
import { Node, Edge } from 'reactflow'
<<<<<<< HEAD
import { MindMapNode } from './api'
=======
import { MindMapNode, MindMapEdge } from './api'
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45

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
