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

### Memory Writer

Memory Writer 已作为 LangGraph 一等节点存在，当前写入范围是：

- SQLite U/R/A 学习画像与对话概念记录。
- Neo4j 对话、根概念与子概念学习地图。

这属于阶段 1 的结构化学习记忆，不等同于阶段 3 的完整分层长期 Memory。跨会话语义记忆、情景记忆、记忆查看/遗忘与持久化 Checkpoint 尚未完成。

## 当前仍未完成

- 阶段 2：图片/PDF/Markdown/TXT 上传接入聊天、结构化切片、混合检索、rerank、回答引用和来源可追溯 GraphRAG。
- 阶段 3：LangGraph 持久化 Checkpoint 与中断恢复、完整分层 Memory、Skills 运行时、DeepStudy MCP Server。
- 多用户认证：当前仍使用 `anonymous`。
- 完整知识图谱高级视图：当前“关系图”是同一学习子图的不同布局；领域 KG Schema 与来源边在阶段 2 实现。
- Verifier 目前不做 LLM 事实核查或引用一致性判断；阶段 2 有真实证据后再扩展。

## 测试状态

- 后端 pytest：20 条测试通过。
- 新增覆盖：真实任务路由、Planner 工具建议、LangGraph 工具循环、普通问题单次模型请求、Gemini 手动 Function Calling、Trace SQLite 持久化。
- 前端 ESLint 与 TypeScript/Vite production build 通过。
- LangGraph 固定为 `>=1.2,<2.0`，实际启动虚拟环境已验证 1.2.10。

## 面试口径

可以说：

> 我用 LangGraph 把原来的线性 Orchestrator 重构成显式 Planner–Executor–Verifier 状态图，通过 Gemini 原生 Function Calling 连接计算器、学习画像、Neo4j 和课程检索工具，并用 SSE 将 Router、Planner、Tool、Verifier、Memory Writer 的安全执行摘要实时展示和持久化。

暂时不要说“完整 GraphRAG、完整分层 Memory、Skills 和 MCP 已经完成”，这些属于后续阶段。
