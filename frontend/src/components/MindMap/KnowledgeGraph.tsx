<<<<<<< HEAD
import { useCallback, useMemo, useEffect } from 'react'
import ReactFlow, {
  Node,
  Edge,
=======
import { useEffect, useCallback } from 'react';
import ReactFlow, {
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
<<<<<<< HEAD
  addEdge,
  Connection,
  useReactFlow,
} from 'reactflow'
import 'reactflow/dist/style.css'
import { MindMapGraph } from '../../types/api'

/**
 * 知识图谱组件
 * 使用 ReactFlow 渲染思维导图
 */
interface KnowledgeGraphProps {
  data: MindMapGraph
  onNodeClick?: (nodeId: string) => void
}

const KnowledgeGraph: React.FC<KnowledgeGraphProps> = ({ 
  data, 
  onNodeClick
}) => {
  const [nodes, setNodes, onNodesChange] = useNodesState(data.nodes as Node[])
  const [edges, setEdges, onEdgesChange] = useEdgesState(data.edges as Edge[])
  const { fitView } = useReactFlow()

  /**
   * 当数据变化时，更新节点和边
   */
  useEffect(() => {
    if (data) {
      setNodes(data.nodes as Node[])
      setEdges(data.edges as Edge[])
    }
  }, [data, setNodes, setEdges])

  /**
   * 当数据变化时，重新拟合视图
   */
  useEffect(() => {
    if (data.nodes.length > 0) {
      setTimeout(() => {
        fitView({ padding: 0.2 })
      }, 100)
    }
  }, [data, fitView])

  /**
   * 处理节点连接
   */
  const onConnect = useCallback(
    (params: Connection) => setEdges((eds) => addEdge(params, eds)),
    [setEdges]
  )

  /**
   * 处理节点点击
   */
  const handleNodeClick = useCallback(
    (event: React.MouseEvent, node: Node) => {
      if (onNodeClick) {
        onNodeClick(node.id)
      }
    },
    [onNodeClick]
  )

  /**
   * 处理节点鼠标悬停
   */
  const handleNodeMouseEnter = useCallback(
    (event: React.MouseEvent, node: Node) => {
      setNodes((nds) =>
        nds.map((n) =>
          n.id === node.id
            ? {
                ...n,
                style: {
                  ...n.style,
                  boxShadow: '0 0 10px rgba(0, 123, 255, 0.5)',
                  transform: 'scale(1.05)',
                  transition: 'all 0.3s ease',
                },
              }
            : n
        )
      )
    },
    [setNodes]
  )

  /**
   * 处理节点鼠标离开
   */
  const handleNodeMouseLeave = useCallback(
    (event: React.MouseEvent, node: Node) => {
      setNodes((nds) =>
        nds.map((n) =>
          n.id === node.id
            ? {
                ...n,
                style: {
                  ...n.style,
                  boxShadow: 'none',
                  transform: 'scale(1)',
                  transition: 'all 0.3s ease',
                },
              }
            : n
        )
      )
    },
    [setNodes]
  )

  /**
   * 节点样式
   */
  const nodeStyles = useMemo(
    () => ({
      default: {
        background: '#fff',
        border: '2px solid #007bff',
        borderRadius: '8px',
        padding: '10px',
        minWidth: '150px',
        fontSize: '14px',
        fontWeight: '500',
      },
      center: {
        background: '#007bff',
        color: 'white',
        border: '2px solid #0056b3',
        borderRadius: '8px',
        padding: '12px',
        minWidth: '200px',
        fontSize: '16px',
        fontWeight: 'bold',
      },
      subject: {
        background: '#fff',
        border: '2px solid #28a745',
        borderRadius: '8px',
        padding: '10px',
        minWidth: '150px',
        fontSize: '14px',
        fontWeight: '500',
      },
      object: {
        background: '#fff',
        border: '2px solid #ffc107',
        borderRadius: '8px',
        padding: '10px',
        minWidth: '150px',
        fontSize: '14px',
        fontWeight: '500',
      },
    }),
    []
  )

  return (
    <div style={{ width: '100%', height: '600px', position: 'relative' }}>
      {/* 知识图谱标题 */}
      <div style={{
        position: 'absolute',
        top: '10px',
        left: '20px',
        zIndex: 1000,
        backgroundColor: 'rgba(255, 255, 255, 0.9)',
        padding: '8px 16px',
        borderRadius: '8px',
        boxShadow: '0 2px 4px rgba(0, 0, 0, 0.1)',
        fontSize: '16px',
        fontWeight: '600',
        color: '#333',
      }}>
        知识图谱
      </div>

      {/* 节点数量统计 */}
      <div style={{
        position: 'absolute',
        top: '10px',
        right: '20px',
        zIndex: 1000,
        backgroundColor: 'rgba(255, 255, 255, 0.9)',
        padding: '6px 12px',
        borderRadius: '8px',
        boxShadow: '0 2px 4px rgba(0, 0, 0, 0.1)',
        fontSize: '12px',
        color: '#666',
      }}>
        节点: {nodes.length} | 边: {edges.length}
      </div>

=======
  MarkerType,
  ConnectionLineType,
  Position,
} from 'reactflow';
import dagre from 'dagre';
import 'reactflow/dist/style.css';

interface MindMapGraphProps {
  data: {
    nodes: any[];
    edges: any[];
  };
}

// --- 1. 智能关键词提取函数 (修复版) ---
const cleanLabel = (text: string): string => {
  if (!text) return '未知节点';
  
  const original = text; // 备份原始文本

  // 去掉常见的提问前缀
  let cleaned = text
    .replace(/^(请|给我|详细|简单)?(介绍|解释|描述|说明)(一下)?/, '') 
    .replace(/^(什么是|何为|什么叫)/, '')
    .replace(/^Test_/, '')
    .trim();

  // 如果是 Markdown 标题，去掉 #
  cleaned = cleaned.replace(/^#+\s*/, '');

  // 👇👇👇 关键修复：如果洗完之后变成空了（比如“详细解释”全被删了），就用回原文！
  if (cleaned.length === 0) {
      return original;
  }
  // 👆👆👆 修复结束

  // 截断逻辑
  if (cleaned.length > 8) {
    return cleaned.slice(0, 8) + '...';
  }
  return cleaned;
};

// --- 2. Dagre 布局算法 ---
const getLayoutedElements = (nodes: any[], edges: any[], direction = 'TB') => {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));

  //稍微调大一点节点尺寸，容纳更多字
  const nodeWidth = 180;
  const nodeHeight = 60;

  dagreGraph.setGraph({ rankdir: direction });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: nodeWidth, height: nodeHeight });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  const targetIds = new Set(edges.map((e) => e.target));

  const layoutedNodes = nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    
    // 判断 Root
    const isRoot = !targetIds.has(node.id);
    
    // 判断是否是“详细解释”节点 (根据 type)
    const isExplanation = node.data?.type === 'explanation';

    return {
      ...node,
      targetPosition: direction === 'TB' ? Position.Top : Position.Left,
      sourcePosition: direction === 'TB' ? Position.Bottom : Position.Right,
      position: {
        x: nodeWithPosition.x - nodeWidth / 2,
        y: nodeWithPosition.y - nodeHeight / 2,
      },
      style: {
        // Root: 绿色; Explanation: 橙色/黄色; Keyword: 蓝色/白色
        background: isRoot ? '#e8f5e9' : (isExplanation ? '#fff3e0' : '#fff'),
        border: isRoot ? '2px solid #2e7d32' : (isExplanation ? '1px solid #ff9800' : '1px solid #ddd'),
        borderRadius: '8px',
        width: '160px',
        height: '50px',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        fontSize: isRoot ? '14px' : '12px',
        fontWeight: isRoot ? 'bold' : 'normal',
        color: '#333',
        boxShadow: isRoot ? '0 4px 8px rgba(0,255,0,0.2)' : '0 2px 4px rgba(0,0,0,0.1)',
      },
      data: { 
        // 这里的 label 会经过 cleanLabel 处理
        label: cleanLabel(node.data.label) 
      }
    };
  });

  return { nodes: layoutedNodes, edges };
};

const KnowledgeGraph = ({ data }: MindMapGraphProps) => {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  useEffect(() => {
    if (data && data.nodes && data.nodes.length > 0) {
      console.log("原始数据:", data);

      const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(
        data.nodes,
        data.edges,
        'TB'
      );

      setNodes(layoutedNodes);
      setEdges(
        layoutedEdges.map((edge: any) => ({
          ...edge,
          type: 'smoothstep',
          animated: true,
          style: { stroke: '#b0bec5' },
          markerEnd: { type: MarkerType.ArrowClosed, color: '#b0bec5' },
        }))
      );
    }
  }, [data, setNodes, setEdges]);

  return (
    <div style={{ width: '100%', height: '100%', minHeight: '500px', background: '#f8f9fa' }}>
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
<<<<<<< HEAD
        onConnect={onConnect}
        onNodeClick={handleNodeClick}
        onNodeMouseEnter={handleNodeMouseEnter}
        onNodeMouseLeave={handleNodeMouseLeave}
        fitView
        attributionPosition="bottom-right"
      >
        <Background gap={12} size={1} />
        <Controls 
          showInteractive={false}
          showFitView={true}
          showZoom={true}
        />
        <MiniMap 
          nodeColor={(n) => {
            if (n.data.type === 'center') return '#007bff'
            if (n.data.type === 'subject') return '#28a745'
            if (n.data.type === 'object') return '#ffc107'
            return '#007bff'
          }}
        />
      </ReactFlow>
    </div>
  )
}

export default KnowledgeGraph
=======
        fitView
        attributionPosition="bottom-right"
      >
        <Background color="#e0e0e0" gap={20} />
        <Controls showInteractive={false} />
        <MiniMap nodeColor={() => '#e0e0e0'} />
      </ReactFlow>
    </div>
  );
};

export default KnowledgeGraph;
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
