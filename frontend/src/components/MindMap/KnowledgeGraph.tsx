import { useEffect, useCallback, useMemo, useRef } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  ConnectionLineType,
  Position,
  Node,
  Edge,
  useReactFlow,
  ReactFlowProvider,
} from 'reactflow';
import dagre from 'dagre';
import 'reactflow/dist/style.css';
// 确保这个路径是对的，根据你的项目结构
import { MindMapGraph } from '../../types/api';
import CustomNode from './CustomNode';

interface KnowledgeGraphProps {
  data: MindMapGraph;
  onNodeClick?: (nodeId: string) => void;
}

// 1. 文本清洗函数
const cleanLabel = (text: string): string => {
  if (!text) return '未知节点';
  const original = text;
  let cleaned = text
    .replace(/^(请|给我|详细|简单)?(介绍|解释|描述|说明)(一下)?/, '')
    .replace(/^(什么是|何为|什么叫)/, '')
    .replace(/^Test_/, '')
    .trim();
  cleaned = cleaned.replace(/^#+\s*/, '');
  if (cleaned.length === 0) return original;
  if (cleaned.length > 12) return cleaned.slice(0, 12) + '...';
  return cleaned;
};

// 2. 布局算法
const getLayoutedElements = (nodes: Node[], edges: Edge[], direction = 'LR') => {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));

  const nodeWidth = 200;
  const nodeHeight = 60;

  dagreGraph.setGraph({
    rankdir: direction,
    nodesep: 40,
    ranksep: 100
  });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: nodeWidth, height: nodeHeight });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  // 颜色判断逻辑
  const targetIds = new Set(edges.map((e) => e.target));
  const sourceIds = new Set(edges.map((e) => e.source));
  
  const layoutedNodes = nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    
    // Root: 没有入边
    const isRoot = !targetIds.has(node.id);
    // Leaf: 没有出边
    const isLeaf = !sourceIds.has(node.id);
    // Focus: 是叶子节点且不是根节点，或者后端显式指定为 explanation
    const isExplanation = node.data?.type === 'explanation' || (isLeaf && !isRoot);

    let variant = 'default';
    if (isRoot) variant = 'root';
    else if (isExplanation) variant = 'explanation';

    return {
      ...node,
      type: 'custom',
      targetPosition: Position.Left,
      sourcePosition: Position.Right,
      position: {
        x: nodeWithPosition.x - nodeWidth / 2,
        y: nodeWithPosition.y - nodeHeight / 2,
      },
      data: {
        ...node.data,
        label: cleanLabel(node.data?.label || node.data?.data?.label || ''),
        variant: variant,
      },
    };
  });

  return { nodes: layoutedNodes, edges };
};

// 3. 内部组件 (包含 Hooks)
const GraphContent = ({ data, onNodeClick }: KnowledgeGraphProps) => {
  const { fitView } = useReactFlow();
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  const nodeTypes = useMemo(() => ({ custom: CustomNode }), []);

  useEffect(() => {
    if (!data || !data.nodes || data.nodes.length === 0) return;

    console.log("正在渲染图谱，节点数:", data.nodes.length);

    const initialNodes: Node[] = data.nodes.map((n: any) => ({
      id: n.id,
      position: { x: 0, y: 0 },
      data: { ...n.data, label: n.data?.label || n.id },
    }));

    const initialEdges: Edge[] = data.edges.map((e: any) => ({
      id: e.id || `${e.source}-${e.target}`,
      source: e.source,
      target: e.target,
      label: e.label,
    }));

    const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(
      initialNodes,
      initialEdges,
      'LR'
    );

    setNodes([...layoutedNodes]);
    
    setEdges(
      layoutedEdges.map((edge) => {
        const relType = edge.label || '';
        const isKeyword = relType === 'HAS_KEYWORD';
        return {
          ...edge,
          type: 'default',
          animated: !isKeyword,
          style: {
            stroke: isKeyword ? '#cbd5e1' : '#60a5fa',
            strokeWidth: isKeyword ? 1 : 2,
            strokeDasharray: isKeyword ? '5,5' : undefined,
          },
        };
      })
    );

    setTimeout(() => {
      fitView({ duration: 800 });
    }, 100);

  }, [
    // 强制依赖 JSON 字符串来检测变化
    JSON.stringify(data.nodes.map(n => n.id)), 
    JSON.stringify(data.edges.map(e => e.id)),
    fitView,
    setNodes,
    setEdges
  ]);

  const handleNodeClick = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      if (onNodeClick) onNodeClick(node.id);
    },
    [onNodeClick]
  );

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onNodeClick={handleNodeClick}
      connectionLineType={ConnectionLineType.SmoothStep}
      fitView
      attributionPosition="bottom-right"
    >
      <Background color="#cbd5e1" gap={20} size={1} />
      <Controls showInteractive={false} className="bg-white shadow-lg border-none" />
      <MiniMap
        nodeColor={(n) => {
          if (n.data.variant === 'root') return '#3b82f6';
          if (n.data.variant === 'explanation') return '#fb923c';
          return '#e2e8f0';
        }}
        maskColor="rgba(240, 240, 240, 0.6)"
        className="bg-white border rounded-lg shadow-sm"
      />
    </ReactFlow>
  );
}; 

// 4. 导出组件 wrapper (确保这里没有嵌套错误)
const KnowledgeGraph: React.FC<KnowledgeGraphProps> = (props) => {
  return (
    <div style={{ width: '100%', height: '100%', minHeight: '600px', background: '#f8fafc' }}>
      <ReactFlowProvider>
        <GraphContent {...props} />
      </ReactFlowProvider>
    </div>
  );
};

export default KnowledgeGraph;