<<<<<<< HEAD
import React, { useState, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import { ContentFragment } from '../../types/api'
import remarkGfm from 'remark-gfm'

/**
 * Markdown 文本片段组件
 * 为代码块和公式注入唯一 ID，支持划词选择
 */
interface TextFragmentProps {
  content: string
  fragments?: ContentFragment[]
  onFragmentSelect?: (fragmentId: string, selectedText: string) => void
=======
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
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
}

const TextFragment: React.FC<TextFragmentProps> = ({
  content,
  fragments = [],
  onFragmentSelect,
}) => {
<<<<<<< HEAD
  const [isSelected, setIsSelected] = useState(false)

  /**
   * 处理文本选择事件
   */
  const handleSelection = () => {
    const selection = window.getSelection()
    if (!selection || selection.rangeCount === 0) {
      setIsSelected(false)
      return
    }

    const selectedText = selection.toString().trim()
    if (!selectedText) {
      setIsSelected(false)
      return
    }

    setIsSelected(true)

    // 查找匹配的 fragment
    const matchedFragment = fragments.find((fragment) =>
      selectedText.includes(fragment.content) || fragment.content.includes(selectedText)
    )

    if (onFragmentSelect) {
      // 如果找到匹配的 fragment，使用其 ID
      // 如果没有找到匹配的 fragment，生成一个临时 ID
      const fragmentId = matchedFragment ? matchedFragment.id : `temp_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
      onFragmentSelect(fragmentId, selectedText)
    }
  }

  // 监听全局鼠标点击，取消选择状态
  useEffect(() => {
    const handleGlobalClick = () => {
      const selection = window.getSelection()
      if (!selection || selection.toString().trim() === '') {
        setIsSelected(false)
      }
    }

    document.addEventListener('click', handleGlobalClick)
    return () => document.removeEventListener('click', handleGlobalClick)
  }, [])
=======
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
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45

  return (
    <div
      onMouseUp={handleSelection}
<<<<<<< HEAD
      style={{
        lineHeight: '1.6',
        fontSize: '1rem',
        position: 'relative',
=======
      className="markdown-body"
      style={{
        lineHeight: '1.6',
        fontSize: '1rem',
        wordBreak: 'break-word',
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
      }}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
<<<<<<< HEAD
          code: ({ className, children, ...props }) => {
            const codeString = String(children).replace(/\n$/, '')
            const fragment = fragments.find((f) => f.content === codeString && f.type === 'code')
            
=======
          // 自定义代码块渲染
          code: ({ node, className, children, ...props }) => {
            const codeString = String(children).replace(/\n$/, '')
            const fragment = fragments.find((f) => f.content === codeString && f.type === 'code')
            const isInline = !className

>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
            return (
              <code
                id={fragment?.id}
                className={className}
                style={{
<<<<<<< HEAD
                  backgroundColor: '#f4f4f4',
                  padding: '2px 4px',
                  borderRadius: '3px',
                  cursor: fragment ? 'pointer' : 'default',
                  transition: 'background-color 0.2s',
=======
                  backgroundColor: isInline ? '#f4f4f4' : 'transparent',
                  padding: isInline ? '2px 4px' : 0,
                  borderRadius: '3px',
                  cursor: fragment ? 'pointer' : 'default',
                  color: isInline ? '#c7254e' : 'inherit',
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
                }}
                {...props}
              >
                {children}
              </code>
            )
          },
<<<<<<< HEAD
=======
          // 自定义 Pre 容器
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
          pre: ({ children }) => {
            return (
              <pre
                style={{
<<<<<<< HEAD
                  backgroundColor: '#f4f4f4',
                  padding: '1rem',
                  borderRadius: '4px',
                  overflow: 'auto',
                  transition: 'background-color 0.2s',
=======
                  backgroundColor: '#f6f8fa',
                  padding: '16px',
                  borderRadius: '6px',
                  overflow: 'auto',
                  border: '1px solid #d0d7de'
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
                }}
              >
                {children}
              </pre>
            )
          },
<<<<<<< HEAD
          p: ({ children, ...props }) => {
            return (
              <p
                style={{
                  transition: 'background-color 0.2s',
                }}
                {...props}
              >
                {children}
              </p>
            )
          },
        }}
      >
        {content}
      </ReactMarkdown>
      
      {/* 划词提示 */}
      {isSelected && (
        <div
          style={{
            position: 'absolute',
            top: '10px',
            right: '10px',
            padding: '4px 8px',
            backgroundColor: 'rgba(37, 99, 235, 0.1)',
            color: '#2563EB',
            borderRadius: '4px',
            fontSize: '12px',
            pointerEvents: 'none',
            transition: 'opacity 0.3s',
          }}
        >
          已选择文本，可进行追问
        </div>
      )}
=======
          // 自定义段落
          p: ({ children }) => <p style={{ marginBottom: '16px' }}>{children}</p>,
        }}
      >
        {processedContent}
      </ReactMarkdown>
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
    </div>
  )
}

<<<<<<< HEAD
export default TextFragment
=======
export default TextFragment
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
