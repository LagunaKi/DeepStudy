import React, { memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';

// 🎨 复刻 Nano Banana 的配色方案
const styles = {
  // 胶囊外壳
  wrapper: {
    padding: '10px 24px',
    borderRadius: '999px', // 完美的圆角胶囊
    borderWidth: '2px',
    borderStyle: 'solid',
    fontSize: '14px',
    fontWeight: 600,
    boxShadow: '0 4px 12px rgba(0,0,0,0.08)', // 柔和的阴影
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    minWidth: '120px',
    textAlign: 'center' as const,
    transition: 'all 0.3s ease',
  },
  // 变体配色
  variants: {
    // 根节点：蓝色系
    root: {
      backgroundColor: '#EFF6FF', // 极浅蓝
      borderColor: '#3B82F6',     // 亮蓝
      color: '#1E40AF',           // 深蓝字
    },
    // 解释/子节点：橙色系 (对应你图里的样子)
    explanation: {
      backgroundColor: '#FFF7ED', // 极浅橙
      borderColor: '#F97316',     // 亮橙
      color: '#9A3412',           // 深橙字
    },
    // 默认
    default: {
      backgroundColor: 'white',
      borderColor: '#E5E7EB',
      color: '#374151',
    }
  }
};

const CustomNode = ({ data, isConnectable }: NodeProps) => {
  // 默认如果是第一层(Root)用蓝色，其他的都用橙色
  // 后端传回来的 type 可能是 'root' 或 'explanation'，如果没有就根据是否是第一个节点判断
  const variant = data.variant || (data.type === 'root' ? 'root' : 'explanation');
  const currentStyle = { ...styles.wrapper, ...styles.variants[variant as keyof typeof styles.variants] };

  return (
    <div style={currentStyle}>
      {/* 隐形连接点，保证连线从边缘发出 */}
      <Handle type="target" position={Position.Left} isConnectable={isConnectable} style={{ opacity: 0 }} />
      
      <div>{data.label}</div>
      
      <Handle type="source" position={Position.Right} isConnectable={isConnectable} style={{ opacity: 0 }} />
    </div>
  );
};

export default memo(CustomNode);