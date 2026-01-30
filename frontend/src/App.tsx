import { Routes, Route, Navigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import Login from './components/Auth/Login'
import Register from './components/Auth/Register'
import ChatInterface from './components/Chat/ChatInterface'
import './App.css'
import 'katex/dist/katex.min.css'


/**
 * 应用主组件
 * 处理路由和认证状态
 */
function App() {
  const [authChecked, setAuthChecked] = useState(false)
  const [authenticated, setAuthenticated] = useState(false)

  // 检查认证状态
  useEffect(() => {
    const checkAuth = () => {
      const token = localStorage.getItem('access_token')
      setAuthenticated(!!token)
      setAuthChecked(true)
    }

    checkAuth()

    // 监听 localStorage 变化（用于跨标签页同步）
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === 'access_token') {
        checkAuth()
      }
    }

    window.addEventListener('storage', handleStorageChange)

    // 定期检查（用于同标签页内的变化）
    const interval = setInterval(checkAuth, 100)

    return () => {
      window.removeEventListener('storage', handleStorageChange)
      clearInterval(interval)
    }
  }, [])

  // 如果还没检查完，显示加载状态或返回 null
  if (!authChecked) {
    return null // 或者显示一个加载指示器
  }

  return (
    <div className="app-background">
      <div className="app-content">
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route
            path="/"
            element={
              authenticated ? <ChatInterface /> : <Navigate to="/login" replace />
            }
          />
        </Routes>
      </div>
    </div>
  )
}

export default App
