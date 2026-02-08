import React, { useState, useEffect, useRef } from 'react';
import { Position, Node } from 'reactflow';
import './ContextMenu.css';

interface EnhancedContextMenuProps {
  isOpen: boolean;
  position: { x: number; y: number };
  nodeId?: string;
  nodeName?: string;
  onClose: () => void;
  onAddNode: (position: { x: number; y: number }, label: string, sourceNodeId?: string) => void;
  onDeleteNode: (nodeId: string) => void;
  onStartConnection: (nodeId: string, position: { x: number; y: number }) => void;
  onEditNode: (nodeId: string, newName: string) => void;
}

const EnhancedContextMenu: React.FC<EnhancedContextMenuProps> = ({
  isOpen,
  position,
  nodeId,
  nodeName,
  onClose,
  onAddNode,
  onDeleteNode,
  onStartConnection,
  onEditNode,
}) => {
  // 添加日志来检查props
  useEffect(() => {
    console.log(`[${new Date().toISOString()}] EnhancedContextMenu props received:`, {
      isOpen,
      nodeId,
      nodeName,
      hasOnEditNode: typeof onEditNode === 'function',
      onEditNodeType: typeof onEditNode
    });
  }, [isOpen, position, nodeId, nodeName, onEditNode]);
  const [showInput, setShowInput] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (showInput && inputRef.current) {
      inputRef.current.focus();
    }
  }, [showInput]);

  useEffect(() => {
    if (isOpen && !showInput) {
      const handleClickOutside = (e: MouseEvent) => {
        if (!(e.target as HTMLElement).closest('.context-menu')) {
          onClose();
        }
      };

      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [isOpen, showInput, onClose]);

  const handleAddNode = () => {
    if (inputValue.trim()) {
      onAddNode(position, inputValue.trim(), nodeId); // 传递源节点ID以创建连接
      setShowInput(false);
      setInputValue('');
      onClose();
    }
  };

  const handleAddStandaloneNode = () => {
    if (inputValue.trim()) {
      onAddNode(position, inputValue.trim()); // 不传递源节点ID，创建独立节点
      setShowInput(false);
      setInputValue('');
      onClose();
    }
  };

  const handleStartConnection = () => {
    if (nodeId) {
      onStartConnection(nodeId, position);
      onClose();
    }
  };

  const handleEditNode = () => {
    console.log(`[${new Date().toISOString()}] 开始编辑节点`, { nodeId, nodeName });
    console.log(`[${new Date().toISOString()}] onEditNode 类型:`, typeof onEditNode);
    console.log(`[${new Date().toISOString()}] onEditNode 是否为函数:`, typeof onEditNode === 'function');
    
    if (nodeId) {
      if (typeof onEditNode === 'function') {
        const currentLabel = nodeName || '';
        console.log(`[${new Date().toISOString()}] 当前节点标签:`, currentLabel);
        
        const newName = window.prompt('请输入新的节点内容:', currentLabel);
        console.log(`[${new Date().toISOString()}] 用户输入的新名称:`, newName);
        
        if (newName !== null) { // 即使是空字符串也要传递给处理函数，让处理函数决定是否接受
          console.log(`[${new Date().toISOString()}] 调用 onEditNode 回调`, { nodeId, newName });
          onEditNode(nodeId, newName);
          console.log(`[${new Date().toISOString()}] 已调用 onEditNode 回调，关闭菜单`);
          onClose();
        } else {
          console.log(`[${new Date().toISOString()}] 用户取消了编辑操作`);
        }
      } else {
        console.error(`[${new Date().toISOString()}] onEditNode 不是一个函数:`, typeof onEditNode);
        console.error(`[${new Date().toISOString()}] 完整的props:`, { nodeId, nodeName, onAddNode, onDeleteNode, onStartConnection, onEditNode });
      }
    } else {
      console.error(`[${new Date().toISOString()}] nodeId 未定义:`, { nodeId });
    }
  };



  const handleDeleteNode = () => {
    if (nodeId) {
      if (window.confirm('确定要删除此节点及其所有子节点吗？')) {
        onDeleteNode(nodeId);
        onClose();
      }
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      if (showInput) {
        handleAddNode();
      }
    } else if (e.key === 'Escape') {
      setShowInput(false);
      setInputValue('');
      onClose();
    }
  };

  if (!isOpen) return null;

  // 防止菜单超出视窗边界
  const adjustedPosition = {
    x: position.x,
    y: position.y
  };

  if (position.x + 200 > window.innerWidth) {
    adjustedPosition.x = window.innerWidth - 210;
  }
  if (position.y + 250 > window.innerHeight) {
    adjustedPosition.y = window.innerHeight - 260;
  }

  return (
    <div 
      className="context-menu" 
      style={{ 
        top: adjustedPosition.y, 
        left: adjustedPosition.x 
      }}
    >
      {!showInput ? (
        <>
          {nodeId && (
            <>
              <div
                className="menu-item"
                onClick={() => setShowInput(true)}
                tabIndex={0}
                role="button"
                aria-label="从当前节点添加子节点"
                onKeyDown={(e) => e.key === 'Enter' && setShowInput(true)}
              >
                添加子节点
              </div>
              <div
                className="menu-item"
                onClick={handleEditNode}
                tabIndex={0}
                role="button"
                aria-label="编辑当前节点内容"
                onKeyDown={(e) => e.key === 'Enter' && handleEditNode()}
              >
                编辑节点内容
              </div>

            </>
          )}
          <div
            className="menu-item"
            onClick={() => {
              setShowInput(true);
            }}
            tabIndex={0}
            role="button"
            aria-label="添加独立节点"
            onKeyDown={(e) => e.key === 'Enter' && setShowInput(true)}
          >
            添加独立节点
          </div>
          {nodeId && (
            <div
              className="menu-item delete-option"
              onClick={handleDeleteNode}
              tabIndex={0}
              role="button"
              aria-label="删除节点"
              onKeyDown={(e) => e.key === 'Enter' && handleDeleteNode()}
            >
              删除节点
            </div>
          )}
        </>
      ) : (
        <div>
          <input
            ref={inputRef}
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={nodeId ? "输入子节点名称" : "输入节点名称"}
            aria-label="输入节点名称"
          />
          <div className="input-actions">
            <button
              className="confirm-btn"
              onClick={nodeId ? handleAddNode : handleAddStandaloneNode}
              tabIndex={0}
              aria-label="确认添加"
              onKeyDown={(e) => e.key === 'Enter' && (nodeId ? handleAddNode : handleAddStandaloneNode)()}
            >
              确认
            </button>
            <button
              className="cancel-btn"
              onClick={() => {
                setShowInput(false);
                setInputValue('');
                onClose();
              }}
              tabIndex={0}
              aria-label="取消"
              onKeyDown={(e) => e.key === 'Enter' && onClose()}
            >
              取消
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default EnhancedContextMenu;