import asyncio
from typing import Any

from google.genai import types
from langgraph.types import StreamWriter

from backend.agent.graph import DeepStudyAgentGraph, build_plan, route_intent
from backend.agent.llm_client import GeminiFunctionCall, GeminiFunctionChunk
from backend.agent.state import AgentState


class FakeProvider:
    def __init__(self, use_tool: bool) -> None:
        self.use_tool = use_tool
        self.calls = 0

    async def generate_stream(self, **_kwargs):
        self.calls += 1
        if self.use_tool and self.calls == 1:
            function_call = GeminiFunctionCall(
                name="calculate_expression",
                arguments={"expression": "12 * (3 + 2)"},
                call_id="call-1",
            )
            yield GeminiFunctionChunk(
                text="",
                function_calls=[function_call],
                model_content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                id="call-1",
                                name=function_call.name,
                                args=function_call.arguments,
                            )
                        )
                    ],
                ),
            )
            return
        for text in ("计算器返回 60，", "因此 12 × (3 + 2) = 60。"):
            yield GeminiFunctionChunk(
                text=text,
                function_calls=[],
                model_content=types.Content(role="model", parts=[types.Part(text=text)]),
            )


class AgentGraphWithoutExternalMemory(DeepStudyAgentGraph):
    async def _memory_writer(
        self, state: AgentState, writer: StreamWriter
    ) -> dict[str, Any]:
        writer(
            {
                "type": "agent",
                "node": "memory_writer",
                "status": "completed",
                "title": "Memory Writer · 测试",
                "summary": "测试中跳过外部存储",
                "details": {},
            }
        )
        return {"memory_updates": []}


class AgentGraphWithEvidence(AgentGraphWithoutExternalMemory):
    async def _retriever(
        self, _state: AgentState, writer: StreamWriter
    ) -> dict[str, Any]:
        items = [
            {
                "citation": 1,
                "document_id": "doc-1",
                "chunk_id": "chunk-1",
                "filename": "lesson.md",
                "version": 1,
                "page": None,
                "section": "Agent",
                "text": "Agent 会根据目标选择工具。",
                "snippet": "Agent 会根据目标选择工具。",
                "score": 0.1,
                "signals": {"bm25_rank": 1},
            }
        ]
        writer({"type": "sources", "items": items})
        return {"retrieved_evidence": items}


def _state(query: str) -> AgentState:
    return {
        "user_id": "anonymous",
        "session_id": "session-1",
        "conversation_id": "conversation-1",
        "query": query,
        "parent_id": None,
        "selected_text": None,
        "parent_context": "",
        "messages": [{"role": "user", "content": query}],
        "tool_calls": [],
        "retrieved_evidence": [],
        "tool_rounds": 0,
    }


def test_router_and_planner_are_real_and_deterministic() -> None:
    assert route_intent("用 Python 实现二分查找") == "code"
    assert route_intent("请推导二次求根公式") == "derivation"
    assert route_intent("什么是 RAG") == "concept"
    assert route_intent("帮我总结第三章的重点") == "review"
    assert route_intent("下一步呢？", has_context=True) == "follow_up"

    plan, tools = build_plan("计算 12 * (3 + 2) 等于多少", "concept")
    assert "calculate_expression" in tools
    assert any("计算器" in step for step in plan)

    profile_plan, profile_tools = build_plan(
        "分析我的薄弱点并推荐下一步学习路径", "learning_profile"
    )
    assert {"get_learning_profile", "query_concept_graph"} <= set(profile_tools)
    assert any("学习画像" in step for step in profile_plan)


def test_langgraph_runs_function_calling_tool_loop_and_trace() -> None:
    provider = FakeProvider(use_tool=True)
    runtime = AgentGraphWithoutExternalMemory(provider)

    async def scenario() -> list[dict[str, Any]]:
        return [event async for event in runtime.stream(_state("计算 12 * (3 + 2)"))]

    events = asyncio.run(scenario())
    nodes = [event.get("node") for event in events if event.get("type") == "agent"]

    assert provider.calls == 2
    assert {"router", "planner", "tool_executor", "verifier", "memory_writer"} <= set(nodes)
    assert any(event.get("type") == "delta" and "60" in event.get("text", "") for event in events)
    tool_event = next(
        event
        for event in events
        if event.get("node") == "tool_executor" and event.get("status") == "completed"
    )
    assert "60" in tool_event["summary"]


def test_simple_question_uses_one_model_request() -> None:
    provider = FakeProvider(use_tool=False)
    runtime = AgentGraphWithoutExternalMemory(provider)

    async def scenario() -> None:
        async for _event in runtime.stream(_state("什么是 Agent？")):
            pass

    asyncio.run(scenario())
    assert provider.calls == 1


def test_retrieved_evidence_emits_sources_and_valid_citation() -> None:
    runtime = AgentGraphWithEvidence(FakeProvider(use_tool=False))

    async def scenario() -> list[dict[str, Any]]:
        return [event async for event in runtime.stream(_state("课程里的 Agent 是什么？"))]

    events = asyncio.run(scenario())
    assert any(event.get("type") == "sources" for event in events)
    assert any(
        event.get("type") == "delta" and "资料依据：[1]" in event.get("text", "")
        for event in events
    )
    verifier = next(event for event in events if event.get("node") == "verifier")
    assert verifier["details"]["citations_valid"] is True


def test_control_intents_skip_irrelevant_retrieval_and_memory_writes() -> None:
    runtime = DeepStudyAgentGraph(FakeProvider(use_tool=False))
    trace: list[dict[str, Any]] = []
    state = _state("你好")
    state["intent"] = "chitchat"

    async def scenario() -> tuple[dict[str, Any], dict[str, Any]]:
        retrieval = await runtime._retriever(state, trace.append)
        memory = await runtime._memory_writer(state, trace.append)
        return retrieval, memory

    retrieval, memory = asyncio.run(scenario())
    assert retrieval == {"retrieved_evidence": []}
    assert memory == {"memory_updates": []}
    memory_event = next(event for event in trace if event.get("node") == "memory_writer")
    assert memory_event["details"] == {"skipped": True, "intent": "chitchat"}
