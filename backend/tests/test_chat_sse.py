import asyncio

from backend.api.routes import chat as chat_route
from backend.api.schemas.request import ChatRequest
from backend.config import settings
from backend.data.conversation_store import get_session
from backend.data.sqlite_db import init_db


class FakeOrchestrator:
    async def process_query_stream(self, **_kwargs):
        yield {
            "type": "meta",
            "conversation_id": "conversation-sse",
            "parent_id": None,
            "runtime": "langgraph",
        }
        yield {
            "type": "agent",
            "node": "router",
            "status": "completed",
            "title": "Router · 任务路由",
            "summary": "识别为概念讲解任务",
            "details": {"intent": "concept"},
        }
        yield {"type": "delta", "text": "这是 SSE 回答。"}
        yield {"type": "end"}


def test_chat_uses_standard_sse_and_persists_trace(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "SQLITE_DB_PATH", str(tmp_path / "sse.db"))
    monkeypatch.setattr(chat_route, "AgentOrchestrator", FakeOrchestrator)

    async def scenario() -> tuple[str, dict]:
        await init_db()
        response = await chat_route.chat(
            ChatRequest(query="什么是 Agent？", session_id="session-sse")
        )
        chunks: list[str] = []
        async for chunk in response.body_iterator:
            chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
        detail = await get_session("session-sse", "anonymous")
        assert detail is not None
        return "".join(chunks), detail

    payload, detail = asyncio.run(scenario())

    assert 'data: {"type": "meta"' in payload
    assert "\n\ndata:" in payload
    assert detail["messages"][1]["content"] == "这是 SSE 回答。"
    assert detail["messages"][1]["agent_trace"][0]["node"] == "router"
