# 实现状态报告

本文档记录 DeepStudy 后端当前实现状态、缺省实现与已知限制。

## 当前实现状态

### 已完成功能

1. **对话与流式输出**
   - `POST /api/chat`：支持首轮提问与划词追问，统一流式返回（`meta` / `delta` / `full` / `end`）
   - 首轮：意图识别 → 策略生成 → 流式输出；后处理做概念提炼、画像更新、Neo4j 写入
   - 划词追问：带 `parent_id`、`ref_fragment_id`、`selected_text`；从 Neo4j 取父节点内容作上下文，流式生成后做递归概念提炼与画像更新

2. **思维导图**
   - `GET /api/mindmap/{conversation_id}`：从 Neo4j 查对话树，融合学习画像（U/R/A、score、times），返回 `MindMapGraph`（nodes/edges）
   - 数据来源：DialogueNode + HAS_CHILD / HAS_KEYWORD，按会话根节点展开

3. **学习画像**
   - SQLite：`concept_profiles`（concept_key, user_id, u, r, a, times, last_practice）、`conversation_concepts`（conversation_id, concept_key, user_id）
   - `GET /api/profile/summary`：当前用户概念列表（按得分排序）
   - `GET /api/profile/weak?limit=`：薄弱概念（按 U 升序）
   - `DELETE /api/profile/concepts`（Body: `{ "concept": "..." }`）：仅删 `concept_profiles`，保留 `conversation_concepts`
   - `GET /api/profile/graph`：画像图结构（节点列表）

4. **学习计划**
   - SQLite：`learning_plan`（user_id, concept_key），用户手动维护的概念列表，多设备/刷新同步
   - `GET /api/profile/plan`：返回学习计划概念名列表
   - `POST /api/profile/plan`（Body: `{ "concept": "..." }`）：将概念加入计划
   - `DELETE /api/profile/plan`（Body: `{ "concept": "..." }`）：从计划移除
   - 前端：学习画像弹层左右双栏（左侧概念列表、右侧学习计划），支持拖拽入计划与「加入计划」「移出计划」；知识图谱接收 `planConcepts`，计划内概念节点以淡绿色卡片背景显示

5. **概念提炼与归一化**
   - 首轮：LLM 提炼 root + children（`CONCEPT_EXTRACTION_FIRST_TURN`），写入画像并记录到 `conversation_concepts`
   - 划词追问：先取父/祖先 node_id（`get_ancestor_node_ids`），再按 `conversation_concepts` 查祖先概念；LLM 提炼（`CONCEPT_EXTRACTION_RECURSIVE`）时鼓励使用已有概念名、可返回 `alias_suggestions`；长度过滤（>20 字丢弃）
   - 归一化：词法规范化 + `profile_aliases.json` 别名字典 + 可选 Embedding 相似度合并；LLM 建议的别名可动态追加到 JSON 并触发 `reload_aliases()`

6. **Neo4j 集成**
   - `save_dialogue_node`、`link_dialogue_nodes`（HAS_CHILD，可选 fragment_id）
   - `get_dialogue_node(node_id)`：单节点
   - `get_dialogue_tree(root_node_id, user_id, max_depth)`：会话子图
   - `get_ancestor_node_ids(node_id, max_depth)`：沿 HAS_CHILD 入边取祖先 node_id 列表

7. **Prompt 管理**
   - 所有 Agent 用到的 Prompt 统一在 `backend/agent/prompts/system_prompts.py`（首轮/递归回答、首轮/递归概念提炼、各策略与知识提取模板）

8. **API 路由**
   - `/api/chat`（流式）、`/api/chat/conversation/{conversation_id}`（对话树）
   - `/api/mindmap/{conversation_id}`（思维导图）
   - `/api/profile/summary`、`/api/profile/weak`、`/api/profile/concepts`（DELETE）、`/api/profile/plan`（GET/POST/DELETE）、`/api/profile/graph`

9. **认证与用户**
   - 当前单用户：`user_id = "anonymous"`，未使用 JWT；auth 路由与 users 表预留

---

## 缺省或简化实现

### 1. 意图识别

**位置**：`backend/agent/intent_router.py`

**当前实现**：`route(query)` 固定返回 `IntentType.CONCEPT`，未调用 LLM。

**影响**：所有请求走 ConceptStrategy，CodeStrategy、DerivationStrategy 仅在有其他入口时才会用到。

**预留**：Few-shot 示例已写在 `_get_few_shot_examples()`，可改为真实 LLM 调用。

### 2. 知识三元组提取

**位置**：`backend/agent/extractors/knowledge_extractor.py`（规则正则）、`orchestrator.py` 中首轮后处理仍会调用

**当前实现**：规则抽取（主谓宾模式），首轮后处理会执行但三元组主要用于日志/预留；首轮概念来自 LLM 提炼（root+children），不是三元组 subject/object。划词追问概念完全由 LLM 提炼，不再用三元组。

**影响**：知识图谱结构来自对话树与概念节点（Neo4j DialogueNode + HAS_KEYWORD 等），不是独立的三元组存储。

### 3. 文本片段（fragments）

**位置**：策略返回的 `AgentResponse.fragments`

**当前实现**：策略可返回空列表；前端划词时由用户选中文本，请求中带 `ref_fragment_id` 与 `selected_text`，不依赖后端片段解析。

**影响**：追问上下文依赖 Neo4j 父节点 content 与前端传入的 selected_text，不依赖后端对代码/公式片段的自动切分。

### 4. 学习诊断报告

**位置**：未实现

**预留**：无 `/api/chat/diagnosis` 或 `/api/profile/diagnosis`；薄弱概念已有 `/api/profile/weak`，无成文诊断报告生成。

---

## 预留或未实现接口

### Data Layer

- **`get_dialogue_context_path(root_node_id, target_node_id)`**：未实现；当前划词追问仅用 `get_dialogue_node(parent_id)` 取父节点内容，以及 `get_ancestor_node_ids` 取祖先 id 用于查 `conversation_concepts`。
- **独立知识三元组存储**：未在 Neo4j 中单独存 subject-relation-object；图谱由对话树与概念节点构成。

### Agent Layer

- **IntentRouter.route()**：缺省返回 CONCEPT，可改为 LLM Few-shot。
- **策略返回的 fragments**：可为空，若需“可点击片段”可在此扩展。

### API Layer

- **`/api/chat/diagnosis` 或 `/api/profile/diagnosis`**：学习诊断报告接口未实现。

---

## 已知限制

### 1. 意图识别固定为 CONCEPT

所有请求均按概念型处理，推导型/代码型未通过意图路由区分。若需按题型分流，需实现 `IntentRouter.route()` 的 LLM 调用。

### 2. 概念提炼依赖 LLM 质量

首轮与递归概念均来自 LLM JSON；若模型输出格式不稳定或含长句，虽有长度过滤与“优先用祖先概念”的约束，仍可能出现噪音概念。别名建议依赖模型是否返回 `alias_suggestions`。

### 3. 对话树查询规模

`get_dialogue_tree` 与 `get_ancestor_node_ids` 均有 `max_depth` 限制（如 6）；会话极深时可能只覆盖部分结构，可按需调整或做分页。

### 4. Neo4j 不可用时的降级

后处理中 Neo4j 写入失败会打日志并降级（如只写 SQLite 画像、不写对话节点）；流式响应已返回，但图谱与对话树会不完整。无“仅 SQLite”的完整降级路径。

### 5. 单用户与认证

当前全局使用 `anonymous`，无多用户隔离；JWT 与 auth 路由存在但未接入主流程。

---

## 后续扩展建议

### 短期

- 实现真正的意图识别（IntentRouter 调用 LLM），按意图走 Code/Derivation 策略。
- 可选：首轮也做三元组抽取并写入 Neo4j（与现有概念节点并存），用于更细粒度图谱。

### 中期

- 学习诊断报告：基于 profile + 对话树生成简要诊断文案，并增加 `/api/profile/diagnosis` 或类似接口。
- 多用户：接入 JWT，user_id 从 token 解析，画像与 conversation_concepts 按 user_id 隔离。

### 长期

- 向量检索：对话或概念向量化，支持语义检索与相似问题推荐。
- 测试与文档：关键路径单测、API 示例与错误码说明。

---

## 技术债务

- 策略类间存在重复模式，可抽公共基类或工具函数。
- 错误响应格式可统一（如统一错误码与 message 结构）。
- 无自动化测试；关键逻辑（如概念归一化、祖先链查询）适合加单测。

---

## 总结

当前后端已实现：流式对话（首轮 + 划词追问）、基于 Neo4j 的对话树与思维导图、基于 SQLite 的学习画像与学习计划（含 conversation_concepts、learning_plan、概念归一化与别名动态追加）、首轮/递归的 LLM 概念提炼与画像更新；前端学习画像弹层双栏与拖拽、图谱学习计划概念淡绿高亮。缺省或未实现部分主要为：真实意图识别、独立知识三元组存储、学习诊断报告接口、多用户认证接入。已知限制集中在意图单一、概念质量依赖 LLM、Neo4j 降级与单用户假设。
