"""FastAPI 与 LangGraph Agent Runtime 之间的兼容编排外壳。"""

import logging
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from backend.agent.graph import DeepStudyAgentGraph
from backend.agent.llm_client import GeminiLLMClient
from backend.agent.model_provider import GeminiModelProvider
from backend.agent.state import AgentState
from backend.api.schemas.response import AgentResponse
from backend.config import settings
from backend.data.conversation_store import get_session
from backend.data.neo4j_client import neo4j_client

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """保留原公开接口，内部实际执行由 LangGraph 负责。"""

    def __init__(self) -> None:
        self.llm = GeminiLLMClient(
            model_name=settings.LLM_MODEL,
            api_key=settings.GEMINI_API_KEY,
            thinking_level=settings.GEMINI_THINKING_LEVEL,
            min_request_interval_seconds=settings.GEMINI_MIN_REQUEST_INTERVAL_SECONDS,
        )
        self.runtime = DeepStudyAgentGraph(GeminiModelProvider(self.llm))

    async def _parent_context(self, parent_id: str | None) -> str:
        if not parent_id:
            return ""
        try:
            node = await neo4j_client.get_dialogue_node(parent_id)
            return str((node or {}).get("content") or "")
        except Exception as exc:
            logger.warning("读取父对话上下文失败，使用会话历史降级: %s", exc)
            return ""

    async def _session_messages(
        self, session_id: str | None, user_id: str
    ) -> list[dict[str, str]]:
        if not session_id:
            return []
        try:
            detail = await get_session(session_id, user_id)
            if not detail:
                return []
            return [
                {"role": message["role"], "content": message["content"]}
                for message in detail["messages"]
                if message.get("status") != "error"
            ][-10:]
        except Exception as exc:
            logger.warning("读取会话历史失败，使用当前问题降级: %s", exc)
            return []

    async def _initial_state(
        self,
        *,
        user_id: str,
        query: str,
        parent_id: str | None,
        session_id: str | None,
        selected_text: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> AgentState:
        actual_session_id = session_id or f"ephemeral-{uuid.uuid4()}"
        return {
            "user_id": user_id,
            "session_id": actual_session_id,
            "conversation_id": str(uuid.uuid4()),
            "query": query,
            "parent_id": parent_id,
            "selected_text": selected_text,
            "attachments": attachments or [],
            "parent_context": await self._parent_context(parent_id),
            "messages": await self._session_messages(session_id, user_id),
            "user_profile": [],
            "task_plan": [],
            "recommended_tools": [],
            "model_contents": [],
            "pending_tool_calls": [],
            "tool_calls": [],
            "retrieved_evidence": [],
            "answer": "",
            "verification_result": {},
            "memory_updates": [],
            "tool_rounds": 0,
        }

    async def process_query_stream(
        self,
        user_id: str,
        query: str,
        parent_id: str | None = None,
        session_id: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        state = await self._initial_state(
            user_id=user_id,
            query=query,
            parent_id=parent_id,
            session_id=session_id,
            attachments=attachments,
        )
        yield {
            "type": "meta",
            "conversation_id": state["conversation_id"],
            "parent_id": parent_id,
            "runtime": "langgraph",
        }
        async for event in self.runtime.stream(state):
            yield event
        yield {"type": "end"}

    async def process_recursive_query_stream(
        self,
        user_id: str,
        parent_id: str,
        fragment_id: str,
        query: str,
        selected_text: str | None = None,
        session_id: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        del fragment_id  # 片段 ID 只用于前端定位，选中文本已进入 AgentState。
        state = await self._initial_state(
            user_id=user_id,
            query=query,
            parent_id=parent_id,
            session_id=session_id,
            selected_text=selected_text,
            attachments=attachments,
        )
        yield {
            "type": "meta",
            "conversation_id": state["conversation_id"],
            "parent_id": parent_id,
            "runtime": "langgraph",
        }
        async for event in self.runtime.stream(state):
            yield event
        yield {"type": "end"}

    async def process_query(
        self,
        user_id: str,
        query: str,
        parent_id: str | None = None,
        session_id: str | None = None,
    ) -> AgentResponse:
        answer_parts: list[str] = []
        conversation_id = ""
        async for event in self.process_query_stream(
            user_id=user_id,
            query=query,
            parent_id=parent_id,
            session_id=session_id,
        ):
            if event.get("type") == "meta":
                conversation_id = str(event.get("conversation_id") or "")
            elif event.get("type") == "delta":
                answer_parts.append(str(event.get("text") or ""))
        return AgentResponse(
            answer="".join(answer_parts),
            conversation_id=conversation_id,
            parent_id=parent_id,
        )
