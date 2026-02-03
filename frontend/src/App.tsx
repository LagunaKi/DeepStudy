import { ReactFlowProvider } from 'reactflow'
import ChatInterface from './components/Chat/ChatInterface'
import './App.css'
import 'katex/dist/katex.min.css'

/**
 * 应用主组件
 * 直接渲染聊天界面（无需登录）
 */
function App() {
  return (
    <ReactFlowProvider>
      <div className="app-background">
        <div className="app-content">
          <ChatInterface />
        </div>
      </div>
    </ReactFlowProvider>
  )
}

export default App
