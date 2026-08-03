"""LangGraph SQLite checkpoint 生命周期与会话恢复能力。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from backend.config import settings


@asynccontextmanager
async def checkpoint_saver() -> AsyncIterator[AsyncSqliteSaver]:
    path = Path(settings.LANGGRAPH_CHECKPOINT_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(str(path)) as saver:
        await saver.setup()
        yield saver


async def checkpoint_status(session_id: str) -> dict[str, Any]:
    async with checkpoint_saver() as saver:
        checkpoint = await saver.aget_tuple(
            {"configurable": {"thread_id": session_id}}
        )
    if checkpoint is None:
        return {"session_id": session_id, "available": False}
    values = checkpoint.checkpoint.get("channel_values", {})
    return {
        "session_id": session_id,
        "available": True,
        "checkpoint_id": checkpoint.config.get("configurable", {}).get("checkpoint_id"),
        "created_at": checkpoint.checkpoint.get("ts"),
        "current_node": checkpoint.metadata.get("source"),
        "step": checkpoint.metadata.get("step"),
        "conversation_id": values.get("conversation_id"),
        "has_answer": bool(values.get("answer")),
        "pending_writes": len(checkpoint.pending_writes or []),
    }


async def delete_checkpoint(session_id: str) -> None:
    async with checkpoint_saver() as saver:
        await saver.adelete_thread(session_id)
