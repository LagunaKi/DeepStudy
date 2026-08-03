# DeepStudy 实现状态报告

本文档按当前代码记录已落地能力与边界，避免把路线图功能误写成已完成。

## 当前架构

```text
React + TypeScript
  -> FastAPI / Server-Sent Events
  -> LangGraph Agent Runtime
  -> Gemini 3 Flash Function Calling
  -> SQLite / Neo4j / Agent Tools
```

FastAPI 是 API 层，LangGraph 是 FastAPI 内部的 Agent 编排运行时，两者不是替代关系。原 `AgentOrchestrator` 现在保留为兼容外壳，实际主流程委托给 `DeepStudyAgentGraph`。

## 阶段 1 已完成

### LangGraph 主链路

已定义显式 `AgentState`，主要字段包括：

- `messages`
- `user_profile`
- `task_plan`
- `recommended_tools`
- `pending_tool_calls`
- `tool_calls`
- `retrieved_evidence`
- `answer`
- `verification_result`
- `memory_updates`

状态图节点为：

```text
START
  -> Router
  -> Memory Retriever
  -> Planner
  -> Agent Model
  -> Tool Executor（按需）
  -> Agent Model（带工具结果）
  -> Verifier
  -> Memory Writer
  -> END
```

Router 使用本地确定性规则区分 `concept`、`derivation`、`code`，不再固定返回 `CONCEPT`，也不会为路由额外消耗免费模型额度。Planner 生成可展示的步骤摘要和建议工具。Verifier 当前是确定性完整性与工具结果检查，不额外调用 LLM。

### Gemini Function Calling

主模型通过可替换的 `AgentModelProvider` 协议接入。当前实现是 `GeminiModelProvider`，使用 Google Gen AI SDK 的原生 Function Calling，关闭 SDK 自动执行函数，由 LangGraph Tool Executor 负责：

1. 将 Pydantic 工具 Schema 发送给 Gemini。
2. 接收模型选择的函数名与结构化参数。
3. 在本地工具注册表执行并记录耗时、状态和摘要。
4. 将函数结果作为 `FunctionResponse` 回传 Gemini。
5. Gemini 基于结果生成用户可读回答。

普通问题没有工具调用时只请求模型一次；需要工具时通常请求两次。正文与 Function Calling 均使用 Gemini 流式接口。每轮最多执行一轮并行工具调用，避免免费额度被无界循环消耗。

已注册工具：

- `calculate_expression`：白名单 AST 计算器，不使用 `eval`。
- `get_learning_profile`：读取 SQLite 学习画像。
- `query_concept_graph`：查询 Neo4j 概念关系。
- `search_course_materials`：检索已有课程资料索引；索引为空时明确降级。

### SSE 与 Agent Trace

`POST /api/chat` 返回标准 `text/event-stream`，事件包括：

- `meta`
- `agent`
- `delta`
- `error`
- `end`

`agent` 事件展示 Router、Planner、Agent Model、Tool Executor、Verifier、Memory Writer 的安全摘要，不展示模型私有 Chain-of-Thought。Trace 随 assistant 消息写入 SQLite 的 `agent_trace` 字段，刷新和切换历史会话后仍可查看。

### 会话与前端

- SQLite 持久化会话、消息、附件元数据和 Agent Trace。
- 支持新建、切换、重命名、删除和刷新恢复。
- 前端使用统一 `ChatTurn`，每轮绑定 user、assistant、status 与 trace。
- 右侧默认是树状学习思维导图，并提供“思维导图 / 关系图”布局切换。
- 区分临时 429、每日免费额度耗尽与 Agent 运行错误。

### 分层 Memory

Memory Retriever 与 Memory Writer 都是 LangGraph 一等节点，当前分为：

- 短期记忆：会话消息历史。
- 运行记忆：SQLite LangGraph Checkpoint，可按 `thread_id` 中断恢复。
- 语义记忆：用户明确表达的目标、偏好、基础或“请记住”的事实。
- 情景记忆：通过验证的学习轮次摘要，不保存整段模型回答。
- 结构化记忆：SQLite U/R/A 学习画像与 Neo4j 学习地图。

长期记忆采用哈希去重、置信度/重要度、时间衰减与词项相关性打分；只把 Top-K
相关记忆注入模型。前端“记忆中心”支持确认、编辑、手动添加和永久遗忘。

## 阶段 2 已完成

- 上传链路支持图片、PDF、Markdown、TXT 与常见代码文件；文件带大小限制、安全文件名、内容哈希去重和同名版本号。
- PDF 保留页码，Markdown 保留标题层级，代码优先按类/函数切片；所有片段保留来源字段。
- 文档状态按 queued、parsing、embedding、indexing、ready/failed 持久化，前端展示进度与失败原因。
- 检索使用 SQLite FTS5 BM25、BGE 向量和 Neo4j 来源图，通过 RRF 融合并按词项覆盖率重排；BGE 不可用时退化为确定性字符 n-gram 向量。
- LangGraph 增加 Retriever 节点，证据在模型生成前注入；回答和历史消息持久化可点击来源，Verifier 检查引用编号。
- 图片附件可通过文件选择或聊天输入框直接粘贴，并通过 Gemini 原生多模态 Part 进入当前问题，不写入文本向量索引。
- Neo4j 使用 Document、Chunk、Concept 与 PART_OF、MENTIONS 来源 Schema；前端“关系图”展示领域图谱，“思维导图”继续展示学习过程。
- `backend/evals` 提供 30 条检索集和 Recall@5、MRR、nDCG@5 回归脚本。

## 阶段 3 已完成

- LangGraph SQLite Checkpoint 与 `resume=true` 节点级恢复。
- 四个学习 Skills：概念讲解、公式推导、生成练习、错题复盘；先读取元数据，命中后再加载正文。
- DeepStudy MCP Server：`search_course`、`query_concept_graph`、`create_quiz` Tools；课程大纲和概念 Resources；两个教学 Prompts。

## 当前仍未完成

- 多用户认证：当前仍使用 `anonymous`。
- Verifier 已检查引用编号存在性，但还不是独立 LLM 事实核查器。

## 测试状态

- 后端 pytest：29 条测试通过，包含跨连接 checkpoint 持久化与失败节点恢复。
- 新增覆盖：真实任务路由、Planner 工具建议、LangGraph 工具循环、普通问题单次模型请求、Gemini 手动 Function Calling、Trace SQLite 持久化。
- 前端 ESLint 与 TypeScript/Vite production build 通过。
- LangGraph 固定为 `>=1.2,<2.0`，实际启动虚拟环境已验证 1.2.10。
- RAG 离线 fixture：30 条查询，Recall@5 1.0000、MRR 0.9444、nDCG@5 0.9587；仅作为代码回归基线。

## 面试口径

可以说：

> 我用 LangGraph 把原来的线性 Orchestrator 重构成显式 Planner–Executor–Verifier 状态图，通过 Gemini 原生 Function Calling 连接计算器、学习画像、Neo4j 和课程检索工具，并用 SSE 将 Router、Planner、Tool、Verifier、Memory Writer 的安全执行摘要实时展示和持久化。

可以进一步补充：

> 阶段 3 将 Memory 做成了可进入推理主链路的分层系统：相关长期记忆先被检索并注入，回答通过验证后 Memory Writer 再保守写入；用户可以查看、修正和永久遗忘。运行时通过 SQLite Checkpoint 支持节点级恢复，并用 Skills 与 MCP 将教学工作流同时开放给内部 Agent 和外部 Host。
