"""LangGraph 共享状态与前端可观察事件协议。"""

from typing import Any, Literal, TypedDict


class AgentTraceEvent(TypedDict, total=False):
    """可以安全展示给用户的 Agent 执行摘要，不包含私有思维链。"""

    type: Literal["agent"]
    node: str
    status: Literal["running", "completed", "failed"]
    title: str
    summary: str
    details: dict[str, Any]
    timestamp: str


class ToolCallRecord(TypedDict, total=False):
    name: str
    call_id: str
    arguments: dict[str, Any]
    status: Literal["success", "error"]
    result: dict[str, Any]
    summary: str
    duration_ms: int


class AgentState(TypedDict, total=False):
    """DeepStudy Agent 在 LangGraph 节点之间传递的显式状态。"""

    user_id: str
    session_id: str
    conversation_id: str
    query: str
    parent_id: str | None
    selected_text: str | None
    attachments: list[dict[str, Any]]
    parent_context: str
    messages: list[dict[str, str]]
    user_profile: list[dict[str, Any]]
    intent: str
    task_plan: list[str]
    recommended_tools: list[str]
    model_contents: list[Any]
    pending_tool_calls: list[dict[str, Any]]
    tool_calls: list[ToolCallRecord]
    retrieved_evidence: list[dict[str, Any]]
    answer: str
    verification_result: dict[str, Any]
    memory_updates: list[dict[str, Any]]
    tool_rounds: int
