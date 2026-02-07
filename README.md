# DeepStudy

基于 ModelScope 的递归学习 Agent：支持首轮/划词追问、知识图谱与学习画像。

## 技术栈

- **前端**: React + TypeScript + ReactFlow + Vite
- **后端**: FastAPI + Python
- **模型**: Qwen/Qwen3-32B（ModelScope OpenAI 兼容 API）
- **数据库**: Neo4j（对话与知识图谱）+ SQLite（用户数据与学习画像）
- **认证**: 当前单用户场景（anonymous），JWT 预留

## 项目结构

```
DeepStudy/
├── frontend/              # React 前端
│   ├── src/
│   │   ├── components/    # Chat、MindMap、Markdown
│   │   ├── services/      # API 封装
│   │   └── types/         # 类型定义
│   └── README.md
├── backend/               # FastAPI 后端
│   ├── api/               # 路由与 schemas
│   ├── agent/             # 编排、意图、策略、提取器、prompts
│   ├── data/              # Neo4j、SQLite、画像与归一化
│   └── README.md
└── README.md
```

## 功能概览

- **流式对话**：首轮提问与划词追问均支持流式输出。
- **知识图谱**：对话树与概念节点写入 Neo4j，侧边栏用 ReactFlow 展示；学习计划内的概念在图谱上以淡绿色卡片高亮。
- **学习画像**：按概念维护 U/R/A 与练习次数；支持查看列表、删除概念；划词追问用 LLM 提炼概念并鼓励归类到父/祖先节点已有概念。
- **学习计划**：用户手动维护的“待重点学习”概念列表，存于后端（多设备/刷新同步）；在学习画像弹层中左侧为概念列表、右侧为学习计划，支持从左侧拖拽或点击「加入计划」，右侧可「移出计划」。
- **概念归一化**：词法规范化 + 别名字典（`profile_aliases.json`）+ 可选 Embedding 合并；LLM 可建议别名并动态追加到别名表。

## 快速开始

### 环境要求

- **Node.js** >= 18
- **Python** >= 3.10
- **Docker**（用于 Neo4j）
- **Conda** 或 **venv**

### 1. 克隆与依赖

```bash
git clone <repository-url>
cd DeepStudy
```

### 2. 后端

```bash
# Python 环境
conda create -n deepstudy python=3.10 && conda activate deepstudy
# 或: python -m venv venv && source venv/bin/activate  # Linux/Mac

# 依赖
pip install -r backend/requirements.txt
```

在项目根或 `backend/` 下创建 `.env`：

```env
MODELSCOPE_API_KEY=your_api_key_here
MODELSCOPE_API_BASE=https://api-inference.modelscope.cn/v1
MODEL_NAME=Qwen/Qwen3-32B
CODER_MODEL_NAME=Qwen/Qwen3-32B

NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=deepstudy123

JWT_SECRET_KEY=your_jwt_secret_key_here
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24

SQLITE_DB_PATH=./backend/storage/deepstudy.db
VECTOR_STORE_PATH=./backend/storage/vector_store

CORS_ORIGINS=["http://localhost:5173","http://localhost:3000"]
API_HOST=0.0.0.0
API_PORT=8000
```

### 3. Neo4j

```bash
docker run -d --name deepstudy-neo4j -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/deepstudy123 neo4j:5.15.0
```

### 4. 启动后端

```bash
# 项目根目录
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

API 文档：http://localhost:8000/docs

### 5. 前端

```bash
cd frontend
npm install
npm run dev
```

前端：http://localhost:5173

## 使用流程

1. **对话**：在聊天框输入问题，AI 流式回答；首轮会做概念提炼并更新学习画像与图谱。
2. **划词追问**：选中回答中的文本，在弹层中输入追问并提交；追问回答会基于父/祖先节点已有概念做 LLM 概念提炼，并可选写入别名建议。
3. **知识图谱**：右侧可展开/收起侧栏，查看当前会话的对话树与概念节点；学习计划中的概念会以淡绿色背景显示。
4. **学习画像与学习计划**：顶部「学习画像」打开弹层。左侧为正在学习的概念列表（U/R/A、练习次数、得分），可「删除」从画像移除或「加入计划」；右侧为学习计划，可将左侧概念拖入或点击加入，计划内可「移出计划」。学习计划存于后端，多设备与刷新后仍保留。

## 开发指南

- [前端开发指南](frontend/README.md)
- [后端开发指南](backend/README.md)

## 开发规范

- 分支：`main` 稳定，功能用 `feature/*`
- 遵循单一职责与 SOLID；修改遵循 KISS
- 后端 Prompt 统一放在 `backend/agent/prompts/system_prompts.py`

## 常见问题

- **Neo4j 连不上**：确认容器运行、端口与 `.env` 中密码一致。
- **ModelScope 报错**：检查 `MODELSCOPE_API_KEY`、`MODELSCOPE_API_BASE` 与网络。
- **前端连不上后端**：确认后端已启动、CORS 包含前端地址；前端 API 基址见 `frontend` README。
