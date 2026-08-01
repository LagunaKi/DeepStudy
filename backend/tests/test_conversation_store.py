import asyncio

from backend.config import settings
from backend.data.conversation_store import (
    add_message,
    create_session,
    delete_session,
    get_session,
    list_sessions,
    rename_session,
)
from backend.data.sqlite_db import init_db


def test_session_crud_and_message_history(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "SQLITE_DB_PATH", str(tmp_path / "history.db"))

    async def scenario() -> None:
        await init_db()
        created = await create_session("anonymous")
        session_id = created["id"]

        await add_message(
            session_id=session_id,
            user_id="anonymous",
            role="user",
            content="请解释检索增强生成的工作原理",
        )
        await add_message(
            session_id=session_id,
            user_id="anonymous",
            role="assistant",
            content="RAG 会先检索证据，再生成答案。",
            conversation_id="conversation-1",
        )

        detail = await get_session(session_id, "anonymous")
        assert detail is not None
        assert detail["title"] == "请解释检索增强生成的工作原理"
        assert [message["role"] for message in detail["messages"]] == [
            "user",
            "assistant",
        ]
        assert detail["messages"][1]["conversation_id"] == "conversation-1"

        sessions = await list_sessions("anonymous")
        assert sessions[0]["message_count"] == 2

        assert await rename_session(session_id, "anonymous", "RAG 学习") is True
        renamed = await get_session(session_id, "anonymous")
        assert renamed is not None
        assert renamed["title"] == "RAG 学习"

        assert await delete_session(session_id, "anonymous") is True
        assert await get_session(session_id, "anonymous") is None

    asyncio.run(scenario())
