import { useEffect, useCallback, useMemo, useRef, useState } from 'react';
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
  Panel,
} from 'reactflow';
import dagre from 'dagre';
import 'reactflow/dist/style.css';
// 确保这个路径是对的，根据你的项目结构
import { MindMapGraph } from '../../types/api';
import CustomNode from './CustomNode';
import EnhancedContextMenu from './EnhancedContextMenu';
import './ContextMenu.css';
import UndoRedoManager, { NodeOperation } from './UndoRedoManager';

interface KnowledgeGraphProps {
  data: MindMapGraph;
  planConcepts?: string[];
  onNodeClick?: (nodeId: string) => void;
  onGraphUpdate?: (updatedData: MindMapGraph) => void;
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
  const targetIds = new Set(edges.map((e: any) => e.target));
  const sourceIds = new Set(edges.map((e: any) => e.source));
  
    const layoutedNodes = nodes.map((node: any) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    
    const isRoot = !targetIds.has(node.id);
    const isLeaf = !sourceIds.has(node.id);
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
        variant,
        inPlan: node.data?.inPlan === true,
      },
    };
  });

  return { nodes: layoutedNodes, edges };
};

// 3. 内部组件 (包含 Hooks)
const GraphContent = ({ data, planConcepts, onNodeClick }: KnowledgeGraphProps) => {
  const { fitView, screenToFlowPosition } = useReactFlow();
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [contextMenu, setContextMenu] = useState<{
    isOpen: boolean;
    position: { x: number; y: number };
    nodeId?: string;
    nodeName?: string;
  }>({ isOpen: false, position: { x: 0, y: 0 } });
  
  const [connectionState, setConnectionState] = useState<{
    isConnecting: boolean;
    sourceNodeId?: string;
    sourcePosition?: { x: number; y: number };
  }>({ isConnecting: false });

  const nodeTypes = useMemo(() => ({ custom: CustomNode }), []);

  // 仅在组件挂载时初始化节点和边
  useEffect(() => {
    if (!data || !data.nodes || data.nodes.length === 0) return;

    const labelOrId = (n: any) => n.data?.label || n.id;
    const initialNodes: Node[] = data.nodes.map((n: any) => ({
      id: n.id,
      position: { x: 0, y: 0 },
      data: {
        ...n.data,
        label: n.data?.label || n.id,
        inPlan: planConcepts && planConcepts.length > 0 ? planConcepts.includes(labelOrId(n)) : false,
      },
    }));

    const initialEdges: Edge[] = data.edges.map((e: any) => ({
      id: e.id || `${e.source}-${e.target}`,
      source: e.source,
      target: e.target,
      label: '', // 清空所有边的标签，但保留连接线本身
    }));

    const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(
      initialNodes,
      initialEdges,
      'LR'
    );

    setNodes([...layoutedNodes]);
    
    setEdges(
      layoutedEdges.map((edge: any) => {
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

  }, []);

  // 处理右键点击事件
  const handlePaneContextMenu = useCallback((event: React.MouseEvent) => {
    console.log(`[${new Date().toISOString()}] 画布右键点击事件`);
    event.preventDefault();
    const position = { x: event.clientX, y: event.clientY };
    console.log(`[${new Date().toISOString()}] 设置右键菜单`, { position });
    setContextMenu({
      isOpen: true,
      position,
      nodeId: undefined,
      nodeName: undefined,
    });
  }, []);
 
  // 处理节点右键点击事件
  const handleNodeContextMenu = useCallback((event: React.MouseEvent, node: Node) => {
    console.log(`[${new Date().toISOString()}] 节点右键点击事件`, { nodeId: node.id, nodeLabel: node.data?.label });
    event.preventDefault();
    event.stopPropagation(); // 防止传播到画布
    const position = { x: event.clientX, y: event.clientY };
    console.log(`[${new Date().toISOString()}] 设置右键菜单`, { nodeId: node.id, nodeName: node.data?.label || node.id, position });
    setContextMenu({
      isOpen: true,
      position,
      nodeId: node.id,
      nodeName: node.data?.label || node.id,
    });
  }, []);

  const handleAddNode = useCallback((position: { x: number; y: number }, label: string, sourceNodeId?: string) => {
    // 将屏幕坐标转换为画布坐标
    const flowPosition = screenToFlowPosition({ x: position.x, y: position.y });
    
    // 创建新节点
    const newNode: Node = {
      id: `node_${Date.now()}`, // 使用时间戳生成唯一ID
      type: 'custom',
      position: flowPosition,
      data: { 
        label: label,
        variant: 'default',
        inPlan: false,
      },
    };

    setNodes(prevNodes => [...prevNodes, newNode]);
    
    // 如果指定了源节点，则创建连接
    if (sourceNodeId) {
      const newEdge = {
        id: `edge_${sourceNodeId}_${newNode.id}`,
        source: sourceNodeId,
        target: newNode.id,
        type: 'default',
        style: { stroke: '#60a5fa', strokeWidth: 2 },
      };
      
      setEdges(prevEdges => [...prevEdges, newEdge]);
      
      // 记录添加节点和边的操作到撤销/重做历史
      UndoRedoManager.push({
        type: 'add',
        nodeData: { node: newNode, edge: newEdge },
      });
    } else {
      // 记录操作到撤销/重做历史
      UndoRedoManager.push({
        type: 'add',
        nodeData: { node: newNode },
      });
    }
  }, [screenToFlowPosition, setNodes, setEdges]);

  const handleDeleteNode = useCallback((nodeId: string) => {
    // 获取要删除的节点和相关边，用于撤销操作
    const nodeToDelete = nodes.find(node => node.id === nodeId);
    const edgesToDelete = edges.filter(edge => 
      edge.source === nodeId || edge.target === nodeId
    );
    
    if (!nodeToDelete) return;

    // 递归查找所有子节点
    const getChildNodeIds = (id: string, allNodes: Node[], allEdges: Edge[]): string[] => {
      const childEdges = allEdges.filter(edge => edge.source === id);
      let childIds: string[] = [];
      
      for (const edge of childEdges) {
        childIds.push(edge.target);
        childIds = childIds.concat(getChildNodeIds(edge.target, allNodes, allEdges));
      }
      
      return childIds;
    };

    const childNodeIds = getChildNodeIds(nodeId, nodes, edges);
    const nodesToRemove = [nodeId, ...childNodeIds];
    
    // 获取所有要删除的节点（包括子节点）
    const nodesToDelete = nodes.filter(node => nodesToRemove.includes(node.id));

    // 删除节点及其所有子节点
    setNodes(prevNodes => 
      prevNodes.filter(node => !nodesToRemove.includes(node.id))
    );

    // 删除相关的边
    setEdges(prevEdges => 
      prevEdges.filter(
        edge => !nodesToRemove.includes(edge.source) && !nodesToRemove.includes(edge.target)
      )
    );
    
    // 记录操作到撤销/重做历史
    UndoRedoManager.push({
      type: 'delete',
      nodeId: nodeId,
      nodeData: {
        node: nodeToDelete,
        childNodes: nodesToDelete.filter(n => n.id !== nodeId), // 除了自己之外的子节点
        edges: edgesToDelete
      }
    });
  }, [setNodes, setEdges, nodes, edges]);

  const handleEditNode = useCallback((nodeId: string, newName: string) => {
    console.log(`[${new Date().toISOString()}] 开始处理节点编辑`, { nodeId, newName });
    
    // 验证参数
    if (!nodeId || typeof newName !== 'string') {
      console.warn('Invalid parameters for handleEditNode:', { nodeId, newName });
      return;
    }
    
    if (!newName || newName.trim() === '') {
      console.log(`[${new Date().toISOString()}] 新名称为空或仅包含空白字符，取消编辑`);
      // 如果新名称为空或只包含空白字符，可以选择通知用户或静默返回
      // 这里我们选择静默返回
      return;
    }
    
    console.log(`[${new Date().toISOString()}] 开始更新节点 ${nodeId} 的标签为 "${newName}"`);
    
    setNodes(prevNodes => {
      // 验证节点是否存在
      const nodeExists = prevNodes.some(node => node.id === nodeId);
      if (!nodeExists) {
        console.warn(`[${new Date().toISOString()}] Node with id ${nodeId} not found`);
        return prevNodes;
      }
      
      console.log(`[${new Date().toISOString()}] 找到节点 ${nodeId}，准备更新标签`);
      
      return prevNodes.map(node => 
        node.id === nodeId 
          ? { 
              ...node, 
              data: { 
                ...node.data, 
                label: newName 
              } 
            } 
          : node
      );
    });
    
    // 记录操作到撤销/重做历史
    const nodeToEdit = nodes.find(node => node.id === nodeId);
    if (nodeToEdit) {
      console.log(`[${new Date().toISOString()}] 记录编辑操作到撤销历史`, { 
        nodeId, 
        oldLabel: nodeToEdit.data.label || '', 
        newLabel: newName 
      });
      
      UndoRedoManager.push({
        type: 'update',
        nodeId: nodeId,
        nodeData: {
          oldLabel: nodeToEdit.data.label || '',
          newLabel: newName
        }
      });
    } else {
      console.warn(`[${new Date().toISOString()}] 无法找到节点进行历史记录`, { nodeId });
    }
  }, [setNodes, nodes]);
  
  // 开始连接过程
  const handleStartConnection = useCallback((sourceNodeId: string, position: { x: number; y: number }) => {
    setConnectionState({
      isConnecting: true,
      sourceNodeId,
      sourcePosition: position,
    });
  }, []);
  
  // 完成连接
  const handleCompleteConnection = useCallback((targetPosition: { x: number; y: number }) => {
    if (!connectionState.isConnecting || !connectionState.sourceNodeId) {
      setConnectionState({ isConnecting: false });
      return;
    }
    
    // 将屏幕坐标转换为画布坐标
    const flowPosition = screenToFlowPosition(targetPosition);
    
    // 创建新节点
    const newNode: Node = {
      id: `node_${Date.now()}`,
      type: 'custom',
      position: flowPosition,
      data: { 
        label: '新节点',
        variant: 'default',
        inPlan: false,
      },
    };

    // 添加新节点
    setNodes(prevNodes => [...prevNodes, newNode]);
    
    // 创建连接边
    const newEdge = {
      id: `edge_${connectionState.sourceNodeId}_${newNode.id}`,
      source: connectionState.sourceNodeId,
      target: newNode.id,
      type: 'default',
      animated: true, // 虚线效果
      style: { stroke: '#94a3b8', strokeWidth: 1, strokeDasharray: '5,5' },
    };
    
    setEdges(prevEdges => [...prevEdges, newEdge]);
    
    // 记录操作到撤销/重做历史
    UndoRedoManager.push({
      type: 'add',
      nodeData: { node: newNode, edge: newEdge },
    });
    
    // 重置连接状态
    setConnectionState({ isConnecting: false });
  }, [connectionState, screenToFlowPosition, setNodes, setEdges]);
  
  // 取消连接
  const handleCancelConnection = useCallback(() => {
    setConnectionState({ isConnecting: false });
  }, []);

  const handleCloseContextMenu = useCallback(() => {
    setContextMenu({ isOpen: false, position: { x: 0, y: 0 } });
  }, []);

  // 处理键盘事件
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      // 处理删除键
      if (event.key === 'Delete') {
        if (contextMenu.nodeId) {
          handleDeleteNode(contextMenu.nodeId);
          setContextMenu({ isOpen: false, position: { x: 0, y: 0 } });
        }
      }
      // 处理 Ctrl+Z 撤销
      else if (event.ctrlKey && event.key === 'z' && !event.shiftKey) {
        event.preventDefault();
        handleUndo();
      }
      // 处理 Ctrl+Shift+Z 或 Ctrl+Y 重做
      else if ((event.ctrlKey && event.shiftKey && event.key === 'z') || 
               (event.ctrlKey && event.key === 'y')) {
        event.preventDefault();
        handleRedo();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [contextMenu.nodeId, handleDeleteNode]);

  const handleUndo = useCallback(() => {
    const operation = UndoRedoManager.undo();
    if (operation) {
      switch (operation.type) {
        case 'add':
          if (operation.nodeData) {
            setNodes(prevNodes => 
              prevNodes.filter(node => node.id !== operation.nodeData.id)
            );
          }
          break;
        case 'delete':
          // 恢复删除的节点和边
          if (operation.nodeData) {
            const { node, childNodes, edges } = operation.nodeData;
            setNodes(prevNodes => {
              const allNodesToAdd = [node, ...childNodes];
              // 避免重复添加节点
              const existingNodeIds = new Set(prevNodes.map((n: any) => n.id));
              const nodesToAdd = allNodesToAdd.filter((n: any) => !existingNodeIds.has(n.id));
              return [...prevNodes, ...nodesToAdd];
            });
            setEdges(prevEdges => {
              // 避免重复添加边
              const existingEdgeIds = new Set(prevEdges.map((e: any) => e.id));
              const edgesToAdd = edges.filter((e: any) => !existingEdgeIds.has(e.id));
              return [...prevEdges, ...edgesToAdd];
            });
          }
          break;
        case 'update':
          // 恢复节点的旧名称
          if (operation.nodeData && operation.nodeId && operation.nodeData.oldLabel !== undefined) {
            setNodes(prevNodes =>
              prevNodes.map(node =>
                node.id === operation.nodeId
                  ? { ...node, data: { ...node.data, label: operation.nodeData.oldLabel } }
                  : node
              )
            );
          }
          break;
      }
    }
  }, [setNodes, setEdges]);

  const handleRedo = useCallback(() => {
    const operation = UndoRedoManager.redo();
    if (operation) {
      switch (operation.type) {
        case 'add':
          if (operation.nodeData) {
            if (operation.nodeData.node) {
              setNodes(prevNodes => {
                // 避免重复添加
                const existingIds = new Set(prevNodes.map((n: any) => n.id));
                if (existingIds.has(operation.nodeData.node.id)) {
                  return prevNodes;
                }
                return [...prevNodes, operation.nodeData.node];
              });
              
              if (operation.nodeData.edge) {
                setEdges(prevEdges => [...prevEdges, operation.nodeData.edge]);
              }
            } else {
              // 兼容旧格式
              setNodes(prevNodes => {
                // 避免重复添加
                const existingIds = new Set(prevNodes.map((n: any) => n.id));
                if (existingIds.has(operation.nodeData.id)) {
                  return prevNodes;
                }
                return [...prevNodes, operation.nodeData];
              });
            }
          }
          break;
        case 'delete':
          if (operation.nodeId) {
            setNodes(prevNodes => 
              prevNodes.filter(node => node.id !== operation.nodeId)
            );
            setEdges(prevEdges => 
              prevEdges.filter(
                edge => edge.source !== operation.nodeId && edge.target !== operation.nodeId
              )
            );
          }
          break;
        case 'update':
          // 应用节点的新名称
          if (operation.nodeData && operation.nodeId && operation.nodeData.newLabel !== undefined) {
            setNodes(prevNodes =>
              prevNodes.map(node =>
                node.id === operation.nodeId
                  ? { ...node, data: { ...node.data, label: operation.nodeData.newLabel } }
                  : node
              )
            );
          }
          break;
      }
    }
  }, [setNodes, setEdges]);

  // 更新思维导图数据，同时保留用户手动添加的节点
  const updateGraphData = useCallback((newData: MindMapGraph) => {
    setNodes(currentNodes => {
      // 保存用户手动添加的节点（ID以'node_'开头的）
      const userAddedNodes = currentNodes.filter(node => node.id.startsWith('node_'));
      
      // 将新数据中的节点与用户添加的节点合并
      const systemNodes = newData.nodes.map((n: any) => ({
        id: n.id,
        position: { x: 0, y: 0 }, // 位置将由布局算法重新计算
        data: {
          ...n.data,
          label: n.data?.label || n.id,
          inPlan: planConcepts && planConcepts.length > 0 ? planConcepts.includes(n.data?.label || n.id) : false,
        },
      }));
      
      return [...systemNodes, ...userAddedNodes];
    });

    setEdges(currentEdges => {
      // 保存用户手动添加的边（ID以'edge_'开头且连接到用户节点的）
      const userAddedEdges = currentEdges.filter(edge => 
        edge.id.startsWith('edge_') && 
        (edge.source.startsWith('node_') || edge.target.startsWith('node_'))
      );
      
      // 将新数据中的边与用户添加的边合并
      const systemEdges = newData.edges.map((e: any) => ({
        id: e.id || `${e.source}-${e.target}`,
        source: e.source,
        target: e.target,
        label: '', // 清空所有边的标签，但保留连接线本身
      }));
      
      return [...systemEdges, ...userAddedEdges];
    });
  }, [setNodes, setEdges, planConcepts]);

  // 监听外部数据更新
  useEffect(() => {
    if (data && data.nodes && data.nodes.length > 0) {
      updateGraphData(data);
    }
  }, [data, updateGraphData]);
  
  // 在每次nodes或edges更新后重新应用布局
  useEffect(() => {
    if (nodes.length > 0) {
      // 为简化处理，我们只对系统节点应用布局，保留用户节点的原始位置
      const systemNodes = nodes.filter(n => !n.id.startsWith('node_'));
      const userNodes = nodes.filter(n => n.id.startsWith('node_'));
      
      const systemEdges = edges.filter(e => 
        !e.id.startsWith('edge_') || 
        (!e.source.startsWith('node_') && !e.target.startsWith('node_'))
      );
      const userEdges = edges.filter(e => 
        e.id.startsWith('edge_') && 
        (e.source.startsWith('node_') || e.target.startsWith('node_'))
      );
      
      if (systemNodes.length > 0) {
        const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(
          systemNodes,
          systemEdges,
          'LR'
        );
        
        // 保留用户节点的原始位置，只更新系统节点的位置
        setNodes([
          ...layoutedNodes,
          ...userNodes.map((node: any) => ({ ...node })) // 确保用户节点不被重新渲染
        ]);
        
        setEdges([
          ...layoutedEdges.map(edge => {
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
          }),
          ...userEdges.map((edge: any) => ({ ...edge })) // 确保用户边不被重新渲染
        ]);
      }
    }
  }, [nodes, edges, getLayoutedElements]);

  const handleNodeClick = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      if (onNodeClick) onNodeClick(node.id);
    },
    [onNodeClick]
  );

  // 处理画布点击事件，用于隐藏菜单
  const handlePaneClick = useCallback(() => {
    // 如果当前有连接状态，则忽略点击
    if (connectionState.isConnecting) {
      return;
    }
    // 隐藏右键菜单
    setContextMenu({ isOpen: false, position: { x: 0, y: 0 } });
  }, [connectionState.isConnecting]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      onNodesChange={onNodesChange} // 确保节点可以拖拽
      onEdgesChange={onEdgesChange}
      onNodeClick={handleNodeClick}
      onNodeContextMenu={handleNodeContextMenu} // 添加节点右键菜单
      onPaneContextMenu={handlePaneContextMenu} // 添加画布右键菜单
      onPaneClick={(event) => {
        // 如果当前有连接状态，则完成连接
        if (connectionState.isConnecting) {
          handleCompleteConnection({ x: event.clientX, y: event.clientY });
        } else {
          // 否则隐藏右键菜单
          handlePaneClick();
        }
      }}
      connectionLineType={ConnectionLineType.SmoothStep}
      fitView
      attributionPosition="bottom-right"
    >
      <Background color="#cbd5e1" gap={20} size={1} />
      <Controls showInteractive={false} className="bg-white shadow-lg border-none" />
      <MiniMap
        nodeColor={(n: any) => {
          if (n.data.variant === 'root') return '#3b82f6';
          if (n.data.variant === 'explanation') return '#fb923c';
          return '#e2e8f0';
        }}
        maskColor="rgba(240, 240, 240, 0.6)"
        className="bg-white border rounded-lg shadow-sm"
      />
      <Panel position="top-left" className="flex gap-2 p-2 bg-white rounded-lg shadow-md">
        <button
          onClick={handleUndo}
          disabled={!UndoRedoManager.canUndo()}
          className={`p-2 rounded-md ${UndoRedoManager.canUndo() ? 'bg-blue-100 hover:bg-blue-200 text-blue-700' : 'bg-gray-100 text-gray-400'}`}
          title="撤销 (Ctrl+Z)"
        >
          ↶
        </button>
        <button
          onClick={handleRedo}
          disabled={!UndoRedoManager.canRedo()}
          className={`p-2 rounded-md ${UndoRedoManager.canRedo() ? 'bg-blue-100 hover:bg-blue-200 text-blue-700' : 'bg-gray-100 text-gray-400'}`}
          title="重做 (Ctrl+Y)"
        >
          ↷
        </button>
      </Panel>
      {connectionState.isConnecting && (
        <div 
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            width: '100vw',
            height: '100vh',
            background: 'transparent',
            zIndex: 9998,
            cursor: 'crosshair',
          }}
          onClick={(e: any) => handleCompleteConnection({ x: e.clientX, y: e.clientY })}
          onContextMenu={(e: any) => {
            e.preventDefault();
            handleCancelConnection();
          }}
        />
      )}
      <EnhancedContextMenu
        isOpen={contextMenu.isOpen}
        position={contextMenu.position}
        nodeId={contextMenu.nodeId}
        nodeName={contextMenu.nodeName}
        onClose={handleCloseContextMenu}
        onAddNode={handleAddNode}
        onDeleteNode={handleDeleteNode}
        onStartConnection={handleStartConnection}
        onEditNode={handleEditNode}
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