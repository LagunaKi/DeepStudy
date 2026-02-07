import { memo, useState, useRef } from 'react';
import { createPortal } from 'react-dom';
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
    root: {
      backgroundColor: '#EFF6FF',
      borderColor: '#3B82F6',
      color: '#1E40AF',
    },
    explanation: {
      backgroundColor: '#FFF7ED',
      borderColor: '#F97316',
      color: '#9A3412',
    },
    default: {
      backgroundColor: 'white',
      borderColor: '#E5E7EB',
      color: '#374151',
    },
    // 学习计划内概念：淡绿色卡片
    plan: {
      backgroundColor: '#DCFCE7', // 淡绿
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

const CustomNode = ({ data, isConnectable }: NodeProps) => {
  const [hovered, setHovered] = useState(false);
  const [cardPosition, setCardPosition] = useState({ top: 0, left: 0 });
  const wrapperRef = useRef<HTMLDivElement>(null);

  const inPlan = (data as any).inPlan === true;
  const variant = inPlan ? 'plan' : (data.variant || (data.type === 'root' ? 'root' : 'explanation'));
  const currentStyle = {
    ...styles.wrapper,
    ...styles.variants[variant as keyof typeof styles.variants],
    position: 'relative' as const,
  };

  const profile = (data as any).profile as
    | { u: number; r: number; a: number; score: number; times: number }
    | undefined;

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