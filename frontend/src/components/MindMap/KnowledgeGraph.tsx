import { useEffect, useCallback } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  MarkerType,
  Position,
} from 'reactflow';
import dagre from 'dagre';
import 'reactflow/dist/style.css';
import { MindMapGraph } from '../../types/api';

interface KnowledgeGraphProps {
  data: MindMapGraph;
  onNodeClick?: (nodeId: string) => void;
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

  // 👇👇👇 关键修复：如果洗完之后变成空了（比如"详细解释"全被删了），就用回原文！
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
    
    // 判断是否是"详细解释"节点 (根据 type)
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
        label: cleanLabel(node.data?.label || node.data?.data?.label || '') 
      }
    };
  });

  return { nodes: layoutedNodes, edges };
};

const KnowledgeGraph: React.FC<KnowledgeGraphProps> = ({ data, onNodeClick }) => {
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
        layoutedEdges.map((edge: any) => {
          // 根据关系类型设置不同的样式
          const relType = edge.label || '';
          const isKeyword = relType === 'HAS_KEYWORD';
          
          // HAS_CHILD: 实线，较粗，主色（蓝色）
          // HAS_KEYWORD: 虚线，较细，辅助色（灰色）
          const edgeStyle = isKeyword
            ? {
                stroke: '#9e9e9e',
                strokeWidth: 1.5,
                strokeDasharray: '5,5', // 虚线
              }
            : {
                stroke: '#64b5f6', // 蓝色
                strokeWidth: 2.5, // 较粗
              };
          
          return {
            ...edge,
            type: 'smoothstep',
            animated: true,
            label: '', // 隐藏标签，通过样式区分
            style: edgeStyle,
            markerEnd: { 
              type: MarkerType.ArrowClosed, 
              color: isKeyword ? '#9e9e9e' : '#64b5f6' 
            },
          };
        })
      );
    }
  }, [data, setNodes, setEdges]);

  // 处理节点点击
  const handleNodeClick = useCallback(
    (_event: React.MouseEvent, node: any) => {
      if (onNodeClick) {
        onNodeClick(node.id);
      }
    },
    [onNodeClick]
  );

  return (
    <div style={{ width: '100%', height: '100%', minHeight: '500px', background: '#f8f9fa' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
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
