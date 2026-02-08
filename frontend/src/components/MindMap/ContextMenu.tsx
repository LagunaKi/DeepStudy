import React, { useState, useEffect, useRef } from 'react';
import './ContextMenu.css'; // 引入CSS样式

interface ContextMenuProps {
  isOpen: boolean;
  position: { x: number; y: number };
  nodeId?: string;
  onClose: () => void;
  onAddNode: (position: { x: number; y: number }, label: string) => void;
  onDeleteNode: (nodeId: string) => void;
}

const ContextMenu: React.FC<ContextMenuProps> = ({
  isOpen,
  position,
  nodeId,
  onClose,
  onAddNode,
  onDeleteNode,
}) => {
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
      onAddNode(position, inputValue.trim());
      setShowInput(false);
      setInputValue('');
      onClose();
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
      handleAddNode();
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
  if (position.y + 200 > window.innerHeight) {
    adjustedPosition.y = window.innerHeight - 210;
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
          <div
            className="menu-item"
            onClick={() => setShowInput(true)}
            tabIndex={0}
            role="button"
            aria-label="添加节点"
            onKeyDown={(e) => e.key === 'Enter' && setShowInput(true)}
          >
            添加节点
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
            placeholder="输入节点名称"
            aria-label="输入节点名称"
          />
          <div className="input-actions">
            <button
              className="confirm-btn"
              onClick={handleAddNode}
              tabIndex={0}
              aria-label="确认添加"
              onKeyDown={(e) => e.key === 'Enter' && handleAddNode()}
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

export default ContextMenu;