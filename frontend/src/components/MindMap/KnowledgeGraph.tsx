import { useEffect, useMemo } from 'react'
import dagre from 'dagre'
import ReactFlow, {
  Background,
  Controls,
  Edge,
  MarkerType,
  Node,
  Position,
  ReactFlowProvider,
  useReactFlow,
} from 'reactflow'
import 'reactflow/dist/style.css'

import { MindMapGraph } from '../../types/api'
import CustomNode from './CustomNode'
import './LearningMap.css'

interface KnowledgeGraphProps {
  data: MindMapGraph
  planConcepts?: string[]
  onNodeClick?: (nodeId: string) => void
  viewMode?: 'mindmap' | 'graph'
}

const NODE_WIDTH = 184
const NODE_HEIGHT = 58

const cleanLabel = (text: string): string => {
  if (!text) return '未命名知识点'
  const cleaned = text
    .replace(/^(请|给我|详细|简单)?(介绍|解释|描述|说明)(一下)?/, '')
    .replace(/^(什么是|何为|什么叫)/, '')
    .replace(/^#+\s*/, '')
    .trim()
  const label = cleaned || text
  return label.length > 18 ? `${label.slice(0, 18)}…` : label
}

const layoutMindMap = (
  graph: MindMapGraph,
  planConcepts: string[],
  viewMode: 'mindmap' | 'graph',
): { nodes: Node[]; edges: Edge[] } => {
  const dagreGraph = new dagre.graphlib.Graph()
  dagreGraph.setDefaultEdgeLabel(() => ({}))
  dagreGraph.setGraph({
    rankdir: viewMode === 'mindmap' ? 'LR' : 'TB',
    align: 'UL',
    nodesep: 34,
    ranksep: 72,
    marginx: 28,
    marginy: 28,
  })

  graph.nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT })
  })
  graph.edges.forEach((edge) => dagreGraph.setEdge(edge.source, edge.target))
  dagre.layout(dagreGraph)

  const targetIds = new Set(graph.edges.map((edge) => edge.target))
  const nodes = graph.nodes.map<Node>((node) => {
    const position = dagreGraph.node(node.id) || { x: 0, y: 0 }
    const label = cleanLabel(String(node.data?.label || node.id))
    const isRoot = !targetIds.has(node.id) || node.data?.type === 'root'
    const inPlan = planConcepts.includes(String(node.data?.label || node.id))

    return {
      id: node.id,
      type: 'custom',
      position: {
        x: position.x - NODE_WIDTH / 2,
        y: position.y - NODE_HEIGHT / 2,
      },
      sourcePosition: viewMode === 'mindmap' ? Position.Right : Position.Bottom,
      targetPosition: viewMode === 'mindmap' ? Position.Left : Position.Top,
      data: {
        ...node.data,
        label,
        variant: isRoot ? 'root' : 'concept',
        inPlan,
      },
    }
  })

  const edges = graph.edges.map<Edge>((edge) => ({
    id: edge.id || `${edge.source}-${edge.target}`,
    source: edge.source,
    target: edge.target,
    type: viewMode === 'mindmap' ? 'smoothstep' : 'default',
    markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: '#94a3b8' },
    style: { stroke: '#94a3b8', strokeWidth: 1.4 },
  }))

  return { nodes, edges }
}

const LearningMapCanvas = ({
  data,
  planConcepts = [],
  onNodeClick,
  viewMode = 'mindmap',
}: KnowledgeGraphProps) => {
  const { fitView } = useReactFlow()
  const nodeTypes = useMemo(() => ({ custom: CustomNode }), [])
  const layout = useMemo(
    () => layoutMindMap(data, planConcepts, viewMode),
    [data, planConcepts, viewMode],
  )

  useEffect(() => {
    if (layout.nodes.length === 0) return
    const timer = window.setTimeout(() => fitView({ padding: 0.22, duration: 450 }), 80)
    return () => window.clearTimeout(timer)
  }, [fitView, layout.nodes.length])

  if (layout.nodes.length === 0) {
    return (
      <div className="learning-map-empty">
        <div className="learning-map-empty-icon">⌁</div>
        <strong>学习地图会在这里生长</strong>
        <span>完成一次提问后，核心概念与分支会自动整理成树。</span>
      </div>
    )
  }

  return (
    <ReactFlow
      nodes={layout.nodes}
      edges={layout.edges}
      nodeTypes={nodeTypes}
      onNodeClick={(_event, node) => onNodeClick?.(node.id)}
      nodesConnectable={false}
      elementsSelectable
      fitView
      minZoom={0.35}
      maxZoom={1.8}
      proOptions={{ hideAttribution: true }}
    >
      <Background color="#dce5f1" gap={24} size={1} />
      <Controls showInteractive={false} position="bottom-right" />
    </ReactFlow>
  )
}

const KnowledgeGraph = (props: KnowledgeGraphProps) => (
  <div className="learning-map-shell">
    <ReactFlowProvider>
      <LearningMapCanvas {...props} />
    </ReactFlowProvider>
  </div>
)

export default KnowledgeGraph
