import React from 'react'
import ReactMarkdown from 'react-markdown'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import remarkGfm from 'remark-gfm'
import 'katex/dist/katex.min.css'
import { ContentFragment } from '../../types/api'

interface TextFragmentProps {
  content: string
  fragments?: ContentFragment[]
  onFragmentSelect?: (fragmentId: string) => void
}

// 预处理 LaTeX 公式：把 \[ \] 变成 $$ $$
const preprocessLaTeX = (content: string) => {
  if (typeof content !== 'string') return ''
  return content
    .replace(/\\\[/g, () => '\n$$\n')
    .replace(/\\\]/g, () => '\n$$\n')
    .replace(/\\\(/g, () => '$')
    .replace(/\\\)/g, () => '$')
}

const TextFragment: React.FC<TextFragmentProps> = ({
  content,
  fragments = [],
  onFragmentSelect,
}) => {
  const handleSelection = () => {
    const selection = window.getSelection()
    if (!selection || selection.rangeCount === 0) return
    const selectedText = selection.toString().trim()
    if (!selectedText) return
    
    const matchedFragment = fragments.find((fragment) =>
      selectedText.includes(fragment.content) || fragment.content.includes(selectedText)
    )
    if (matchedFragment && onFragmentSelect) {
      onFragmentSelect(matchedFragment.id)
    }
  }

  const processedContent = preprocessLaTeX(content)

  return (
    <div
      onMouseUp={handleSelection}
      className="markdown-body"
      style={{
        lineHeight: '1.6',
        fontSize: '1rem',
        wordBreak: 'break-word',
      }}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          // 自定义代码块渲染
          code: ({ node, className, children, ...props }) => {
            const codeString = String(children).replace(/\n$/, '')
            const fragment = fragments.find((f) => f.content === codeString && f.type === 'code')
            const isInline = !className

            return (
              <code
                id={fragment?.id}
                className={className}
                style={{
                  backgroundColor: isInline ? '#f4f4f4' : 'transparent',
                  padding: isInline ? '2px 4px' : 0,
                  borderRadius: '3px',
                  cursor: fragment ? 'pointer' : 'default',
                  color: isInline ? '#c7254e' : 'inherit',
                }}
                {...props}
              >
                {children}
              </code>
            )
          },
          // 自定义 Pre 容器
          pre: ({ children }) => {
            return (
              <pre
                style={{
                  backgroundColor: '#f6f8fa',
                  padding: '16px',
                  borderRadius: '6px',
                  overflow: 'auto',
                  border: '1px solid #d0d7de'
                }}
              >
                {children}
              </pre>
            )
          },
          // 自定义段落
          p: ({ children }) => <p style={{ marginBottom: '16px' }}>{children}</p>,
        }}
      >
        {processedContent}
      </ReactMarkdown>
    </div>
  )
}

export default TextFragment