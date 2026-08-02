# DeepStudy 后端

FastAPI + LangGraph + Gemini 3 Flash，负责 Agent 编排、Function Calling、SSE、知识图谱写入与学习画像。

## 技术栈

- **框架**: FastAPI
- **Agent Runtime**: LangGraph 1.2（显式 `AgentState`）
- **LLM**: Google Gen AI SDK（`agent/llm_client.py`）
- **模型**: Gemini 3 Flash 免费 API 层（主模型与代码模型可配置）
- **存储**: Neo4j（对话与图谱）、SQLite（用户表、概念画像、对话–概念关联）
- **认证**: JWT 预留；当前单用户为 `anonymous`

## 项目结构

```
backend/
├── api/
│   ├── routes/
│   │   ├── chat.py        # 流式对话、划词追问
│   │   ├── mindmap.py     # 按 conversationId 返回图谱
│   │   ├── profile.py     # 学习画像 summary/weak/delete、图谱视图
│   │   └── knowledge.py   # 知识相关（若有）
│   └── schemas/           # 请求/响应模型
├── agent/
│   ├── orchestrator.py    # FastAPI 到 LangGraph 的兼容外壳
│   ├── graph.py           # Router/Planner/Agent/Tool/Verifier/Memory 状态图
│   ├── state.py           # AgentState 与 Trace 协议
│   ├── tools.py           # Pydantic 工具注册表与执行器
│   ├── model_provider.py  # 可替换模型 Provider
│   ├── concept_extractor.py   # 不额外调用 LLM 的学习地图概念提取
│   ├── intent_router.py   # 意图识别（concept/code/derivation）
│   ├── activity_classifier.py  # 学习活动分类（explain/derive/...）
│   ├── llm_client.py      # Gemini 异步与流式调用
│   ├── prompts/
│   │   └── system_prompts.py   # 首轮/递归回答与各策略 Prompt
│   ├── strategies/        # ConceptStrategy、CodeStrategy、DerivationStrategy
│   └── extractors/        # knowledge_extractor（规则三元组，首轮仍用）
├── data/
│   ├── neo4j_client.py    # 对话节点、HAS_CHILD、get_ancestor_node_ids、get_dialogue_tree
│   ├── sqlite_db.py       # users、concept_profiles、conversation_concepts
│   ├── profile_store.py   # 画像 CRUD、概念归一化、conversation_concepts、别名追加
│   ├── profile_aliases.json    # 别名字典（可被 LLM 建议动态追加）
│   ├── profile_config.json    # 活动权重、embedding 阈值等
│   └── vector_store.py    # Embedding（归一化用）
├── config.py
├── main.py
└── requirements.txt
```

## 快速开始

```bash
pip install -r requirements.txt
```

配置 `.env`（见根目录 README 或下方环境变量）。启动 Neo4j 后：

```bash
# 项目根目录
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

API 文档：http://localhost:8000/docs

## 核心流程

`Router → Planner → Gemini Function Calling → Tool Executor（按需）→ Verifier → Memory Writer`。普通问答只请求模型一次；使用工具时将本地结果回传模型再生成回答。

## API 概览

### 聊天

- **POST /api/chat**  
  Body: `query`, `parent_id?`, `ref_fragment_id?`, `selected_text?`, `session_id`  
  标准 SSE：`type: meta | agent | delta | error | end`。`agent` 包含可安全展示的节点摘要，Trace 会随历史消息持久化。

### 思维导图

- **GET /api/mindmap/{conversation_id}**  
  返回 `{ nodes, edges }`（当前会话子图）。

### 学习画像

- **GET /api/profile/summary**  
  当前用户概念列表：`concept`, `u`, `r`, `a`, `times`, `last_practice`, `score`。
- **GET /api/profile/weak?limit=**  
  薄弱概念（按 U 升序）。
- **DELETE /api/profile/concepts**  
  Body: `{ "concept": "概念名" }`，仅删 `concept_profiles`，保留 `conversation_concepts`。
- **GET /api/profile/graph**  
  画像图结构（节点列表等）。

## 数据库

### SQLite

- **users**：预留。
- **concept_profiles**：`(concept_key, user_id)`，维度 U/R/A、times、last_practice。
- **conversation_concepts**：`(conversation_id, concept_key, user_id)`，记录某轮对话涉及的概念，用于递归追问时查祖先概念。

### Neo4j

- 节点：`DialogueNode`，属性含 `node_id`, `user_id`, `role`, `content`, `intent`, `mastery_score`, `title`, `type`。
- 关系：`(parent)-[:HAS_CHILD]->(child)`，用于对话树与祖先链查询（`get_ancestor_node_ids`）。

## Agent Tools

- `calculate_expression`
- `get_learning_profile`
- `query_concept_graph`
- `search_course_materials`

工具输入由 Pydantic 校验，执行器记录参数、状态、耗时和结果摘要。

## 环境变量

- **Gemini**: `GEMINI_API_KEY`、`LLM_MODEL`、`LLM_CODER_MODEL`、`GEMINI_THINKING_LEVEL`
- **Neo4j**: `NEO4J_URI`、`NEO4J_USER`、`NEO4J_PASSWORD`
- **JWT**: `JWT_SECRET_KEY`、`JWT_ALGORITHM`、`JWT_EXPIRATION_HOURS`
- **存储**: `SQLITE_DB_PATH`、`VECTOR_STORE_PATH`
- **CORS**: `CORS_ORIGINS`（JSON 数组）
- **服务**: `API_HOST`、`API_PORT`

## 开发规范

- 类型注解与 JSDoc 风格注释；错误用 HTTPException + 日志。
- 模块单一职责；Prompt 与配置集中管理。

## 常见问题

- **Neo4j 连接失败**：检查容器、端口、密码与 `NEO4J_AUTH`。
- **Gemini 401/403**：确认 `GEMINI_API_KEY` 来自 Google AI Studio。
- **Gemini 429**：所有模型调用共用请求节流器；临时限流按服务端 `retryDelay` 冷却；每日额度耗尽单独提示，不再错误显示短倒计时。免费层默认每 4 秒最多启动一次请求。
- **导入错误**：在项目根目录运行 uvicorn，保证 `backend` 包可被解析。

更多实现细节见 [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)（若存在）。
