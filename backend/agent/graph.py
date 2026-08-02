"""DeepStudy 的 LangGraph Planner–Executor–Verifier Agent Runtime。"""

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any, Literal

from google.genai import types
from langgraph.graph import END, START, StateGraph
from langgraph.types import StreamWriter

from backend.agent.activity_classifier import classify_activity
from backend.agent.concept_extractor import extract_concept_structure
from backend.agent.model_provider import AgentModelProvider
from backend.agent.state import AgentState, AgentTraceEvent
from backend.agent.tools import ToolRegistry
from backend.data.neo4j_client import neo4j_client
from backend.data.profile_store import apply_learning_event_to_concepts

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trace(
    writer: StreamWriter,
    *,
    node: str,
    title: str,
    summary: str,
    status: Literal["running", "completed", "failed"] = "completed",
    details: dict[str, Any] | None = None,
) -> AgentTraceEvent:
    event: AgentTraceEvent = {
        "type": "agent",
        "node": node,
        "status": status,
        "title": title,
        "summary": summary,
        "details": details or {},
        "timestamp": _now(),
    }
    writer(event)
    return event


def route_intent(query: str) -> str:
    """无额外模型调用的真实任务路由。"""
    normalized = query.lower()
    code_keywords = (
        "代码",
        "编程",
        "python",
        "javascript",
        "typescript",
        "java",
        "c++",
        "报错",
        "bug",
        "函数实现",
        "算法实现",
    )
    derivation_keywords = (
        "推导",
        "证明",
        "公式",
        "为什么成立",
        "计算过程",
        "求解",
        "derive",
        "prove",
    )
    if any(keyword in normalized for keyword in code_keywords):
        return "code"
    if any(keyword in normalized for keyword in derivation_keywords):
        return "derivation"
    return "concept"


def build_plan(query: str, intent: str) -> tuple[list[str], list[str]]:
    """生成可展示的任务计划摘要与建议工具，不生成/暴露 CoT。"""
    steps = ["识别问题目标与期望输出"]
    tools: list[str] = []
    normalized = query.lower()

    if re.search(r"\d\s*[-+*/%^]\s*\d|计算|等于多少|结果是多少", normalized):
        tools.append("calculate_expression")
        steps.append("使用计算器核对数值")
    if any(word in normalized for word in ("我的掌握", "学习画像", "薄弱", "个性化")):
        tools.append("get_learning_profile")
        steps.append("读取学习画像进行个性化")
    if any(word in normalized for word in ("前置知识", "关联概念", "知识图谱", "学习路径")):
        tools.append("query_concept_graph")
        steps.append("查询概念图谱关系")
    if any(word in normalized for word in ("课程资料", "上传的", "文档", "讲义", "课件")):
        tools.append("search_course_materials")
        steps.append("检索课程资料证据")

    intent_step = {
        "code": "组织可运行代码与关键说明",
        "derivation": "逐步组织推导并检查关键等式",
        "concept": "按直觉、定义、示例和易错点组织讲解",
    }[intent]
    steps.extend([intent_step, "验证答案覆盖度与工具结果"])
    return steps, tools


def _system_instruction(state: AgentState) -> str:
    intent_instruction = {
        "code": "提供可运行代码、关键逻辑和必要的边界情况。",
        "derivation": "逐步推导，说明每一步依据，并核对符号与结论。",
        "concept": "用直觉、准确定义、例子和常见误区帮助学习者理解。",
    }[state["intent"]]
    plan = "；".join(state.get("task_plan", []))
    recommended = state.get("recommended_tools", [])
    tool_hint = "、".join(recommended) if recommended else "无强制工具"
    return f"""你是 DeepStudy 自适应学习 Agent。{intent_instruction}

执行计划摘要：{plan}
建议工具：{tool_hint}

要求：
1. 只有在工具能提高正确性或需要读取外部数据时才调用工具；普通概念问答直接回答。
2. 不能声称使用了未实际调用的工具或不存在的资料。
3. 工具返回失败时明确说明降级，不要编造结果。
4. 回答使用 Markdown，优先清晰、准确、适合学习，不展示内部思维链。
"""


def _to_gemini_contents(state: AgentState) -> list[types.Content]:
    contents: list[types.Content] = []
    for message in state.get("messages", [])[-10:]:
        content = str(message.get("content") or "").strip()
        if not content:
            continue
        role = "model" if message.get("role") == "assistant" else "user"
        contents.append(types.Content(role=role, parts=[types.Part(text=content)]))

    query = state["query"]
    parent_context = state.get("parent_context", "").strip()
    selected_text = (state.get("selected_text") or "").strip()
    if selected_text:
        query = f"选中的内容：{selected_text}\n追问：{query}"
    if parent_context:
        query = f"上一段回答上下文：{parent_context[:1500]}\n\n当前问题：{query}"

    if not contents or contents[-1].role != "user":
        contents.append(types.Content(role="user", parts=[types.Part(text=query)]))
    elif query not in (contents[-1].parts[0].text or ""):
        contents.append(types.Content(role="user", parts=[types.Part(text=query)]))
    return contents


class DeepStudyAgentGraph:
    """组装并运行 DeepStudy 的显式 LangGraph 状态机。"""

    def __init__(
        self,
        provider: AgentModelProvider,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        self.provider = provider
        self.tools = tool_registry or ToolRegistry()
        self.graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(AgentState)
        builder.add_node("router", self._router)
        builder.add_node("planner", self._planner)
        builder.add_node("agent_model", self._agent_model)
        builder.add_node("tool_executor", self._tool_executor)
        builder.add_node("verifier", self._verifier)
        builder.add_node("memory_writer", self._memory_writer)
        builder.add_edge(START, "router")
        builder.add_edge("router", "planner")
        builder.add_edge("planner", "agent_model")
        builder.add_conditional_edges(
            "agent_model",
            self._next_after_model,
            {"tools": "tool_executor", "verify": "verifier"},
        )
        builder.add_edge("tool_executor", "agent_model")
        builder.add_edge("verifier", "memory_writer")
        builder.add_edge("memory_writer", END)
        return builder.compile(name="deepstudy-agent")

    async def _router(self, state: AgentState, writer: StreamWriter) -> dict[str, Any]:
        intent = route_intent(state["query"])
        labels = {"code": "代码实现", "derivation": "推导求解", "concept": "概念讲解"}
        _trace(
            writer,
            node="router",
            title="Router · 任务路由",
            summary=f"识别为{labels[intent]}任务",
            details={"intent": intent},
        )
        return {"intent": intent}

    async def _planner(self, state: AgentState, writer: StreamWriter) -> dict[str, Any]:
        plan, recommended = build_plan(state["query"], state["intent"])
        _trace(
            writer,
            node="planner",
            title="Planner · 执行计划",
            summary=" → ".join(plan),
            details={"steps": plan, "recommended_tools": recommended},
        )
        return {"task_plan": plan, "recommended_tools": recommended}

    async def _agent_model(self, state: AgentState, writer: StreamWriter) -> dict[str, Any]:
        contents = state.get("model_contents") or _to_gemini_contents(state)
        allow_tools = state.get("tool_rounds", 0) < MAX_TOOL_ROUNDS
        _trace(
            writer,
            node="agent_model",
            title="Agent · Gemini 3 Flash",
            summary="正在选择工具或生成回答",
            status="running",
            details={"function_calling": allow_tools, "available_tools": self.tools.names},
        )
        next_contents = list(contents)
        pending: list[dict[str, Any]] = []
        streamed_answer: list[str] = []
        async for chunk in self.provider.generate_stream(
            contents=contents,
            system_instruction=_system_instruction(state),
            tool_declarations=self.tools.declarations(),
            allow_tools=allow_tools,
        ):
            if chunk.model_content is not None:
                next_contents.append(chunk.model_content)
            if chunk.text:
                streamed_answer.append(chunk.text)
                writer({"type": "delta", "text": chunk.text})
            for call in chunk.function_calls:
                record = {
                    "name": call.name,
                    "arguments": call.arguments,
                    "call_id": call.call_id,
                }
                identity = (record["call_id"], record["name"], str(record["arguments"]))
                existing = {
                    (item["call_id"], item["name"], str(item["arguments"]))
                    for item in pending
                }
                if identity not in existing:
                    pending.append(record)
        if pending and allow_tools:
            _trace(
                writer,
                node="agent_model",
                title="Agent · Function Calling",
                summary=f"模型选择了 {len(pending)} 个工具调用",
                details={"tools": [call["name"] for call in pending]},
            )
            return {"model_contents": next_contents, "pending_tool_calls": pending}

        answer = "".join(streamed_answer).strip()
        if not answer:
            successful = [
                call["summary"]
                for call in state.get("tool_calls", [])
                if call.get("status") == "success"
            ]
            fallback = "；".join(successful) if successful else "请换一种问法重试。"
            answer = f"工具执行完成。{fallback}"
        if not streamed_answer:
            writer({"type": "delta", "text": answer})
        _trace(
            writer,
            node="agent_model",
            title="Agent · 回答生成",
            summary="已基于当前上下文与工具结果生成回答",
            details={"used_tools": [call["name"] for call in state.get("tool_calls", [])]},
        )
        return {
            "answer": answer,
            "model_contents": next_contents,
            "pending_tool_calls": [],
        }

    @staticmethod
    def _next_after_model(state: AgentState) -> Literal["tools", "verify"]:
        return "tools" if state.get("pending_tool_calls") else "verify"

    async def _tool_executor(
        self, state: AgentState, writer: StreamWriter
    ) -> dict[str, Any]:
        records: list[dict[str, Any]] = []
        response_parts: list[types.Part] = []
        evidence = list(state.get("retrieved_evidence", []))
        for call in state.get("pending_tool_calls", []):
            _trace(
                writer,
                node="tool_executor",
                title=f"Tool · {call['name']}",
                summary="正在执行工具",
                status="running",
                details={"arguments": call.get("arguments", {})},
            )
            record = await self.tools.execute(
                call["name"],
                call.get("arguments", {}),
                user_id=state["user_id"],
                call_id=call.get("call_id", ""),
            )
            records.append(record)
            if record["status"] == "success":
                evidence.append(
                    {
                        "tool": record["name"],
                        "summary": record["summary"],
                        "result": record["result"],
                    }
                )
            _trace(
                writer,
                node="tool_executor",
                title=f"Tool · {record['name']}",
                summary=record["summary"],
                status="completed" if record["status"] == "success" else "failed",
                details={
                    "arguments": record["arguments"],
                    "duration_ms": record["duration_ms"],
                },
            )
            response_parts.append(
                types.Part(
                    function_response=types.FunctionResponse(
                        id=record.get("call_id") or None,
                        name=record["name"],
                        response={"result": record["result"], "status": record["status"]},
                    )
                )
            )

        contents = [
            *state.get("model_contents", []),
            types.Content(role="user", parts=response_parts),
        ]
        return {
            "model_contents": contents,
            "pending_tool_calls": [],
            "tool_calls": [*state.get("tool_calls", []), *records],
            "retrieved_evidence": evidence,
            "tool_rounds": state.get("tool_rounds", 0) + 1,
        }

    async def _verifier(self, state: AgentState, writer: StreamWriter) -> dict[str, Any]:
        answer = state.get("answer", "").strip()
        tool_calls = state.get("tool_calls", [])
        failures = [call for call in tool_calls if call.get("status") == "error"]
        checks = {
            "answer_present": bool(answer),
            "question_covered": len(answer) >= 20,
            "tool_results_available": not tool_calls or len(failures) < len(tool_calls),
            "failed_tools": [call["name"] for call in failures],
        }
        passed = checks["answer_present"] and checks["question_covered"]
        summary = "回答完整性检查通过" if passed else "回答较短或不完整，建议重试"
        if failures:
            summary += f"；{len(failures)} 个工具已降级"
        result = {"passed": passed, "checks": checks, "summary": summary}
        _trace(
            writer,
            node="verifier",
            title="Verifier · 结果校验",
            summary=summary,
            status="completed" if passed else "failed",
            details=checks,
        )
        return {"verification_result": result}

    async def _memory_writer(
        self, state: AgentState, writer: StreamWriter
    ) -> dict[str, Any]:
        answer = state.get("answer", "")
        structure = extract_concept_structure(state["query"], answer)
        root = str(structure.get("root") or "").strip()
        children = [
            str(item).strip()
            for item in structure.get("children", [])
            if str(item).strip()
        ]
        concepts = list(dict.fromkeys([item for item in [root, *children] if item]))
        updates: list[dict[str, Any]] = []
        try:
            activity = await classify_activity(None, state["query"], answer[:300]) or "explain"
            delta = await apply_learning_event_to_concepts(
                raw_concepts=concepts,
                activity=activity,
                user_id=state["user_id"],
                conversation_id=state["conversation_id"],
            )
            updates.append(
                {
                    "scope": "learning_profile",
                    "concepts": concepts,
                    "activity": activity,
                    "delta": {"u": delta.u, "r": delta.r, "a": delta.a},
                }
            )
        except Exception as exc:
            logger.warning("学习画像写入失败，已降级: %s", exc, exc_info=True)

        try:
            await asyncio.wait_for(self._persist_learning_map(state, root, children), timeout=3)
            updates.append({"scope": "learning_map", "concepts": concepts})
        except Exception as exc:
            logger.warning("Neo4j 学习地图写入失败，已降级: %s", exc)

        _trace(
            writer,
            node="memory_writer",
            title="Memory Writer · 学习记忆",
            summary=(
                f"已记录 {len(concepts)} 个学习概念"
                if updates
                else "记忆存储不可用，本轮回答不受影响"
            ),
            status="completed" if updates else "failed",
            details={"concepts": concepts, "updated_scopes": [u["scope"] for u in updates]},
        )
        return {"memory_updates": updates}

    async def _persist_learning_map(
        self, state: AgentState, root: str, children: list[str]
    ) -> None:
        conversation_id = state["conversation_id"]
        user_id = state["user_id"]
        root_label = root or state["query"][:40]
        user_node_id = f"{conversation_id}_root"
        await neo4j_client.save_dialogue_node(
            node_id=user_node_id,
            user_id=user_id,
            role="user",
            content=state["query"],
            intent=state["intent"],
            title=root_label,
            type="root",
        )
        await neo4j_client.save_dialogue_node(
            node_id=conversation_id,
            user_id=user_id,
            role="assistant",
            content=state.get("answer", ""),
            intent=state["intent"],
            title="详细解释",
            type="explanation",
        )
        await neo4j_client.link_dialogue_nodes(user_node_id, conversation_id)
        if state.get("parent_id"):
            await neo4j_client.link_dialogue_nodes(state["parent_id"], user_node_id)
        for index, concept in enumerate(children):
            child_id = f"{conversation_id}_concept_{index}"
            await neo4j_client.save_dialogue_node(
                node_id=child_id,
                user_id=user_id,
                role="assistant",
                content=concept,
                title=concept,
                type="keyword",
            )
            await neo4j_client.link_dialogue_nodes(user_node_id, child_id)

    async def stream(self, initial_state: AgentState):
        async for part in self.graph.astream(
            initial_state,
            config={"configurable": {"thread_id": initial_state["session_id"]}},
            stream_mode="custom",
            version="v2",
        ):
            if part["type"] == "custom":
                yield part["data"]
