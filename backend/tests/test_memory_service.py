import asyncio

from backend.config import settings
from backend.data.sqlite_db import get_db_connection, init_db
from backend.memory.service import MemoryService


def test_long_term_memory_dedupes_retrieves_updates_and_forgets(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "SQLITE_DB_PATH", str(tmp_path / "memory.db"))
    service = MemoryService()

    async def scenario() -> None:
        await init_db()
        candidates = await service.extract_semantic_candidates(
            "请记住：我偏好先看直觉例子，再看公式。"
        )
        assert candidates[0]["user_confirmed"] is True

        first, created = await service.upsert(
            user_id="anonymous",
            scope="semantic",
            kind=candidates[0]["kind"],
            content=candidates[0]["content"],
            source="conversation",
            source_session_id="session-a",
            confidence=candidates[0]["confidence"],
            importance=candidates[0]["importance"],
            user_confirmed=True,
        )
        assert created is True
        second, created_again = await service.upsert(
            user_id="anonymous",
            scope="semantic",
            kind=candidates[0]["kind"],
            content=candidates[0]["content"],
            source="conversation",
            source_session_id="session-a",
        )
        assert created_again is False
        assert second["id"] == first["id"]

        episode_one, _ = await service.upsert(
            user_id="anonymous", scope="episodic", kind="learning_turn",
            content="学习了 RAG；活动类型为 explain",
            source="agent", source_conversation_id="turn-1",
        )
        episode_two, _ = await service.upsert(
            user_id="anonymous", scope="episodic", kind="learning_turn",
            content="学习了 RAG；活动类型为 explain",
            source="agent", source_conversation_id="turn-2",
        )
        assert episode_one["id"] != episode_two["id"]

        retrieved = await service.retrieve(
            "公式应该怎么学？",
            user_id="anonymous",
            current_session_id="session-b",
        )
        assert retrieved and retrieved[0]["id"] == first["id"]

        updated = await service.update(
            first["id"],
            user_id="anonymous",
            content="我偏好先看一个直觉例子，再学习公式。",
            importance=1.0,
        )
        assert updated and updated["importance"] == 1.0
        assert await service.delete(first["id"], user_id="anonymous") is True
        remaining = await service.list(user_id="anonymous")
        assert {item["scope"] for item in remaining} == {"episodic"}
        async with get_db_connection() as db:
            cursor = await db.execute(
                "SELECT action FROM agent_memory_audit WHERE memory_id = ? ORDER BY created_at",
                (first["id"],),
            )
            assert "delete" in [row["action"] for row in await cursor.fetchall()]

    asyncio.run(scenario())
