import { memo, useState, useRef } from 'react';
import { createPortal } from 'react-dom';
import { Handle, Position, NodeProps } from 'reactflow';

const styles = {
  wrapper: {
    padding: '11px 14px',
    borderRadius: '12px',
    borderWidth: '1px',
    borderStyle: 'solid',
    fontSize: '12px',
    fontWeight: 650,
    lineHeight: 1.35,
    boxShadow: '0 5px 16px rgba(15, 23, 42, 0.08)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: '184px',
    minHeight: '50px',
    textAlign: 'center' as const,
    transition: 'transform 0.18s ease, box-shadow 0.18s ease',
  },
  // 变体配色
  variants: {
    root: {
      background: 'linear-gradient(135deg, #1D4ED8, #4F46E5)',
      borderColor: '#3B82F6',
      color: '#FFFFFF',
    },
    explanation: {
      backgroundColor: '#FFFFFF',
      borderColor: '#D8E1EC',
      color: '#334155',
    },
    concept: {
      backgroundColor: '#FFFFFF',
      borderColor: '#BFDBFE',
      color: '#1E3A5F',
    },
    default: {
      backgroundColor: 'white',
      borderColor: '#E5E7EB',
      color: '#374151',
    },
    // 学习计划内概念：淡绿色卡片
    plan: {
      backgroundColor: '#ECFDF5',
      borderColor: '#22C55E',
      color: '#166534',
    },
  }
};

/** 三角雷达图：U/R/A 三条轴，顶点在上/右下/左下，数值 0–1 决定内三角形状 */
const TriangleRadar = ({ u, r, a }: { u: number; r: number; a: number }) => {
  const size = 80;
  const cx = size / 2;
  const cy = size / 2;
  const R = size * 0.4; // 轴长
  // 三个轴方向：上(-90°)、右下(30°)、左下(150°)，对应 U、R、A
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const x = (angleDeg: number, value: number) => cx + R * value * Math.cos(toRad(angleDeg));
  const y = (angleDeg: number, value: number) => cy + R * value * Math.sin(toRad(angleDeg));
  const top = { x: x(-90, 1), y: y(-90, 1) };
  const right = { x: x(30, 1), y: y(30, 1) };
  const left = { x: x(150, 1), y: y(150, 1) };
  const innerTop = { x: x(-90, u), y: y(-90, u) };
  const innerRight = { x: x(30, r), y: y(30, r) };
  const innerLeft = { x: x(150, a), y: y(150, a) };
  const outer = `${top.x},${top.y} ${right.x},${right.y} ${left.x},${left.y}`;
  const inner = `${innerTop.x},${innerTop.y} ${innerRight.x},${innerRight.y} ${innerLeft.x},${innerLeft.y}`;
  return (
    <svg width={size} height={size} style={{ display: 'block', margin: '0 auto 6px' }}>
      <polygon points={outer} fill="none" stroke="#e5e7eb" strokeWidth="1.5" />
      <polygon points={inner} fill="rgba(59,130,246,0.35)" stroke="#3b82f6" strokeWidth="1.2" />
      <text x={cx} y={12} textAnchor="middle" fontSize="9" fill="#64748b">U</text>
      <text x={size - 4} y={cy + 4} textAnchor="end" fontSize="9" fill="#64748b">R</text>
      <text x={4} y={cy + 4} textAnchor="start" fontSize="9" fill="#64748b">A</text>
    </svg>
  );
};

const CARD_WIDTH = 200;

interface CustomNodeData {
  label: string;
  inPlan?: boolean;
  variant?: keyof typeof styles.variants;
  type?: string;
  profile?: { u: number; r: number; a: number; score: number; times: number };
}

const CustomNode = ({ data, isConnectable }: NodeProps<CustomNodeData>) => {
  const [hovered, setHovered] = useState(false);
  const [cardPosition, setCardPosition] = useState({ top: 0, left: 0 });
  const wrapperRef = useRef<HTMLDivElement>(null);

  const inPlan = data.inPlan === true;
  const variant = inPlan ? 'plan' : (data.variant || (data.type === 'root' ? 'root' : 'concept'));
  const currentStyle = {
    ...styles.wrapper,
    ...styles.variants[variant as keyof typeof styles.variants],
    position: 'relative' as const,
  };

  const profile = data.profile;

  const handleMouseEnter = () => {
    if (wrapperRef.current) {
      const rect = wrapperRef.current.getBoundingClientRect();
      setCardPosition({
        top: rect.bottom + 6,
        left: rect.left + rect.width / 2 - CARD_WIDTH / 2,
      });
    }
    setHovered(true);
  };

  const cardEl =
    profile && hovered ? (
      <div
        role="tooltip"
        style={{
          position: 'fixed',
          top: cardPosition.top,
          left: cardPosition.left,
          width: CARD_WIDTH,
          backgroundColor: 'white',
          borderRadius: '12px',
          padding: '10px 12px',
          boxShadow: '0 12px 28px rgba(15,23,42,0.22)',
          fontSize: '12px',
          textAlign: 'center',
          zIndex: 2147483647,
          pointerEvents: 'none',
        }}
      >
        <div style={{ fontWeight: 700, marginBottom: '6px' }}>学习画像</div>
        <TriangleRadar u={profile.u} r={profile.r} a={profile.a} />
        <div style={{ color: '#6b7280' }}>练习 {profile.times} 次</div>
      </div>
    ) : null;

  return (
    <>
      <div
        ref={wrapperRef}
        style={currentStyle}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={() => setHovered(false)}
      >
        <Handle type="target" position={Position.Left} isConnectable={isConnectable} style={{ opacity: 0 }} />
        <div>{data.label}</div>
        <Handle type="source" position={Position.Right} isConnectable={isConnectable} style={{ opacity: 0 }} />
      </div>
      {typeof document !== 'undefined' && document.body ? createPortal(cardEl, document.body) : cardEl}
    </>
  );
};

export default memo(CustomNode);
