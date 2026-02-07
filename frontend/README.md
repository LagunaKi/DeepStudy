# DeepStudy 前端

React + TypeScript + Vite，聊天界面、知识图谱侧栏与学习画像弹层。

## 技术栈

- **框架**: React 18 + TypeScript
- **构建**: Vite
- **HTTP**: Axios（API 封装）
- **图谱**: ReactFlow
- **Markdown**: react-markdown + KaTeX

## 项目结构

```
frontend/
├── src/
│   ├── components/
│   │   ├── Chat/           # ChatInterface：对话、划词追问、学习画像
│   │   ├── MindMap/        # KnowledgeGraph、CustomNode
│   │   └── Markdown/       # TextFragment（Markdown + 公式 + 片段选择）
│   ├── services/           # api.ts：chat、mindMap、profile API
│   ├── types/              # api.ts、reactflow 类型
│   └── hooks/              # useAuth（预留）
├── public/
└── package.json
```

## 快速开始

```bash
npm install
npm run dev
```

开发地址：http://localhost:5173

```bash
npm run build
npm run preview
```

构建产物在 `dist/`。

## 核心组件

### App.tsx

根组件：渲染背景与 `ChatInterface`，无路由与登录（当前单用户）。

### ChatInterface

- **消息区**：用户消息与 AI 流式回答；Enter 发送，Shift+Enter 换行。
- **侧栏**：「显示/隐藏图谱」切换；知识图谱由 ReactFlow 渲染，数据来自 `/api/mindmap/{conversationId}` 轮询。
- **划词追问**：在回答中选中文本 → 弹出追问框 → 输入问题提交，请求流式 `/api/chat`（带 `parent_id`、`ref_fragment_id`、`selected_text`）。
- **学习画像与学习计划**：「学习画像」打开弹层，左右双栏。左侧为概念列表（`GET /api/profile/summary`），每条可「删除」或「加入计划」；支持将左侧概念**拖拽**到右侧。右侧为学习计划（`GET /api/profile/plan`），可「移出计划」。计划存后端，多设备同步。

### TextFragment

- 渲染 Markdown，代码块与公式注入 `frag_xxx` ID。
- 监听选中文本，回调 `onFragmentSelect(fragmentId, selectedText)` 用于划词追问。

### KnowledgeGraph

- 接收 `MindMapGraph`（nodes/edges）与可选 `planConcepts`（学习计划概念名列表）；用 ReactFlow 展示，节点掌握度等样式见 CustomNode。若节点对应概念在 `planConcepts` 中，CustomNode 以淡绿色卡片背景显示。

## API 封装（services/api.ts）

- **chatAPI**
  - `sendMessageStream(data, onChunk)`：流式发送，`data` 含 `query`、`parent_id`、`ref_fragment_id`、`selected_text`、`session_id`。
  - `getConversationTree(conversationId)`：获取对话树（当前未在前端主流程使用）。
- **mindMapAPI**
  - `getMindMap(conversationId)`：获取思维导图 nodes/edges。
- **profileAPI**
  - `getSummary()`：学习画像概念列表。
  - `deleteConcept(concept)`：从画像删除该概念（请求体 `{ concept }`）。
  - `getPlan()`：学习计划概念名列表。
  - `addToPlan(concept)`：将概念加入学习计划。
  - `removeFromPlan(concept)`：从学习计划移除概念。

## 环境变量

可选 `.env.local`：

```env
VITE_API_BASE_URL=http://localhost:8000/api
```

未设置时默认使用 `/api`（依赖 Vite 或 Nginx 代理到后端）。

## 开发与规范

- ESLint；TypeScript 严格类型。
- 组件职责单一；错误在界面提示（如画像加载失败、删除失败）。

## 常见问题

- **接口 404/跨域**：确认后端已启动、CORS 包含前端地址；开发时可用 Vite 代理将 `/api` 指向 `http://localhost:8000`。
- **图谱不更新**：对话流中收到 `conversation_id` 后会轮询 mindmap；确认侧栏已打开。
