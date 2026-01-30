import { useState, useRef, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { authAPI } from '../../services/api'
import { UserLogin } from '../../types/api'

/**
 * 登录组件
 */
const Login = () => {
  const navigate = useNavigate()
  const usernameInputRef = useRef<HTMLInputElement>(null)
  const [formData, setFormData] = useState<UserLogin>({
    username: '',
    password: '',
  })
  const [error, setError] = useState<string>('')
  const [loading, setLoading] = useState<boolean>(false)

  // 页面加载时自动聚焦用户名输入框
  useEffect(() => {
    usernameInputRef.current?.focus()
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      await authAPI.login(formData)
      navigate('/')
    } catch (err: any) {
      setError(err.response?.data?.message || '登录失败，请检查用户名和密码')
    } finally {
      setLoading(false)
    }
  }

  // 统一样式常量
  const containerStyle: React.CSSProperties = {
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    minHeight: '100vh',
    backgroundColor: 'transparent',
  }

  const cardStyle: React.CSSProperties = {
    backgroundColor: 'white',
    padding: '24px',
    borderRadius: '8px',
    boxShadow: '0 2px 10px rgba(0,0,0,0.1)',
    width: '100%',
    maxWidth: '400px',
  }

  const headerStyle: React.CSSProperties = {
    marginBottom: '24px',
    textAlign: 'center',
  }

  const titleStyle: React.CSSProperties = {
    fontSize: '24px',
    fontWeight: 600,
    color: '#111827',
    margin: 0,
    marginBottom: '8px',
  }

  const subtitleStyle: React.CSSProperties = {
    fontSize: '14px',
    color: '#6B7280',
    margin: 0,
  }

  const formGroupStyle: React.CSSProperties = {
    marginBottom: '16px',
  }

  const labelStyle: React.CSSProperties = {
    display: 'block',
    fontSize: '14px',
    fontWeight: 500,
    color: '#374151',
    marginBottom: '6px',
  }

  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '12px',
    border: '1px solid #D1D5DB',
    borderRadius: '6px',
    fontSize: '16px',
    outline: 'none',
    transition: 'border-color 0.2s',
  }

  const inputFocusStyle: React.CSSProperties = {
    borderColor: '#2563EB',
    boxShadow: '0 0 0 3px rgba(37, 99, 235, 0.1)',
  }

  const errorStyle: React.CSSProperties = {
    color: '#EF4444',
    backgroundColor: '#FEE2E2',
    padding: '8px',
    borderRadius: '4px',
    fontSize: '14px',
    marginBottom: '12px',
  }

  const buttonStyle: React.CSSProperties = {
    width: '100%',
    padding: '12px',
    backgroundColor: '#2563EB',
    color: 'white',
    border: 'none',
    borderRadius: '6px',
    fontSize: '16px',
    fontWeight: 500,
    cursor: loading ? 'not-allowed' : 'pointer',
    opacity: loading ? 0.6 : 1,
    transition: 'background-color 0.2s',
  }

  const buttonHoverStyle: React.CSSProperties = {
    backgroundColor: '#1D4ED8',
  }

  const footerStyle: React.CSSProperties = {
    marginTop: '16px',
    textAlign: 'center',
    fontSize: '14px',
    color: '#6B7280',
  }

  const linkStyle: React.CSSProperties = {
    color: '#2563EB',
    textDecoration: 'none',
  }

  return (
    <div style={containerStyle}>
      <div style={cardStyle}>
        {/* Header 区 */}
        <div style={headerStyle}>
          <h2 style={titleStyle}>登录</h2>
          <p style={subtitleStyle}>继续你的递归学习之旅</p>
        </div>

        {/* Form 区 */}
        <form onSubmit={handleSubmit}>
          <div style={formGroupStyle}>
            <label style={labelStyle}>用户名</label>
            <input
              ref={usernameInputRef}
              type="text"
              value={formData.username}
              onChange={(e) => {
                setFormData({ ...formData, username: e.target.value })
                setError('')
              }}
              required
              disabled={loading}
              style={{
                ...inputStyle,
                ...(loading ? { backgroundColor: '#F3F4F6', cursor: 'not-allowed' } : {}),
              }}
              onFocus={(e) => {
                e.target.style.borderColor = '#2563EB'
                e.target.style.boxShadow = '0 0 0 3px rgba(37, 99, 235, 0.1)'
              }}
              onBlur={(e) => {
                e.target.style.borderColor = '#D1D5DB'
                e.target.style.boxShadow = 'none'
              }}
            />
          </div>

          <div style={formGroupStyle}>
            <label style={labelStyle}>密码</label>
            <input
              type="password"
              value={formData.password}
              onChange={(e) => {
                setFormData({ ...formData, password: e.target.value })
                setError('')
              }}
              required
              disabled={loading}
              style={{
                ...inputStyle,
                ...(loading ? { backgroundColor: '#F3F4F6', cursor: 'not-allowed' } : {}),
              }}
              onFocus={(e) => {
                e.target.style.borderColor = '#2563EB'
                e.target.style.boxShadow = '0 0 0 3px rgba(37, 99, 235, 0.1)'
              }}
              onBlur={(e) => {
                e.target.style.borderColor = '#D1D5DB'
                e.target.style.boxShadow = 'none'
              }}
            />
          </div>

          {/* 错误提示 */}
          {error && (
            <div style={errorStyle} role="alert">
              {error}
            </div>
          )}

          {/* 提交按钮 */}
          <button
            type="submit"
            disabled={loading}
            style={buttonStyle}
            onMouseEnter={(e) => {
              if (!loading) {
                e.currentTarget.style.backgroundColor = '#1D4ED8'
              }
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = '#2563EB'
            }}
          >
            {loading ? '登录中...' : '登录'}
          </button>
        </form>

        {/* Footer 区 */}
        <div style={footerStyle}>
          <span>还没有账号？</span>
          <Link
            to="/register"
            style={linkStyle}
            onMouseEnter={(e) => {
              e.currentTarget.style.textDecoration = 'underline'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.textDecoration = 'none'
            }}
          >
            注册
          </Link>
        </div>
      </div>
    </div>
  )
}

export default Login
