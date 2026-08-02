"""SQLite-backed chat session and message history."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.config import settings
from backend.data.sqlite_db import get_db_connection

DEFAULT_SESSION_TITLE = "新对话"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _title_from_query(query: str) -> str:
    title = " ".join(query.split()).strip()
    if not title:
        return DEFAULT_SESSION_TITLE
    return title if len(title) <= 32 else f"{title[:32]}…"


async def create_session(
    user_id: str,
    title: str = DEFAULT_SESSION_TITLE,
    session_id: str | None = None,
) -> dict[str, Any]:
    session_id = session_id or str(uuid4())
    timestamp = _now()
    normalized_title = title.strip() or DEFAULT_SESSION_TITLE

    async with get_db_connection() as db:
        await db.execute(
            """
            INSERT INTO chat_sessions (id, user_id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, user_id, normalized_title, timestamp, timestamp),
        )
        await db.commit()

    return {
        "id": session_id,
        "title": normalized_title,
        "created_at": timestamp,
        "updated_at": timestamp,
        "message_count": 0,
    }


async def ensure_session(session_id: str, user_id: str) -> None:
    timestamp = _now()
    async with get_db_connection() as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO chat_sessions (id, user_id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, user_id, DEFAULT_SESSION_TITLE, timestamp, timestamp),
        )
        await db.commit()


async def list_sessions(user_id: str) -> list[dict[str, Any]]:
    async with get_db_connection() as db:
        cursor = await db.execute(
            """
            SELECT s.id, s.title, s.created_at, s.updated_at,
                   COUNT(m.id) AS message_count
            FROM chat_sessions AS s
            LEFT JOIN chat_messages AS m ON m.session_id = s.id
            WHERE s.user_id = ?
            GROUP BY s.id
            ORDER BY s.updated_at DESC
            """,
            (user_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]


async def get_session(session_id: str, user_id: str) -> dict[str, Any] | None:
    async with get_db_connection() as db:
        session_cursor = await db.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM chat_sessions
            WHERE id = ? AND user_id = ?
            """,
            (session_id, user_id),
        )
        session = await session_cursor.fetchone()
        if session is None:
            return None

        message_cursor = await db.execute(
            """
            SELECT id, role, content, conversation_id, parent_id, status,
                   agent_trace, sources, created_at
            FROM chat_messages
            WHERE session_id = ?
            ORDER BY created_at ASC, rowid ASC
            """,
            (session_id,),
        )
        messages = []
        for row in await message_cursor.fetchall():
            message = dict(row)
            try:
                message["agent_trace"] = json.loads(message.get("agent_trace") or "[]")
            except (json.JSONDecodeError, TypeError):
                message["agent_trace"] = []
            try:
                message["sources"] = json.loads(message.get("sources") or "[]")
            except (json.JSONDecodeError, TypeError):
                message["sources"] = []
            messages.append(message)

        attachment_cursor = await db.execute(
            """
            SELECT id, message_id, document_id, filename, mime_type, size_bytes,
                   status, progress, error, created_at, updated_at
            FROM message_attachments WHERE session_id = ?
            ORDER BY created_at ASC
            """,
            (session_id,),
        )
        attachments_by_message: dict[str, list[dict[str, Any]]] = {}
        for row in await attachment_cursor.fetchall():
            attachment = dict(row)
            message_id = attachment.pop("message_id", None)
            if message_id:
                attachments_by_message.setdefault(message_id, []).append(attachment)
        for message in messages:
            message["attachments"] = attachments_by_message.get(message["id"], [])

    result = dict(session)
    result["messages"] = messages
    result["message_count"] = len(messages)
    return result


async def rename_session(session_id: str, user_id: str, title: str) -> bool:
    normalized_title = title.strip()
    if not normalized_title:
        return False

    async with get_db_connection() as db:
        cursor = await db.execute(
            """
            UPDATE chat_sessions
            SET title = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (normalized_title[:80], _now(), session_id, user_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def delete_session(session_id: str, user_id: str) -> bool:
    storage_paths: list[str] = []
    async with get_db_connection() as db:
        owner_cursor = await db.execute(
            "SELECT 1 FROM chat_sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        )
        if await owner_cursor.fetchone() is None:
            return False

        attachment_cursor = await db.execute(
            "SELECT storage_path FROM message_attachments WHERE session_id = ?",
            (session_id,),
        )
        storage_paths = [
            str(row["storage_path"])
            for row in await attachment_cursor.fetchall()
            if row["storage_path"]
        ]

        # Explicit deletes keep behavior correct even if an older SQLite connection
        # was created without PRAGMA foreign_keys enabled.
        chunks_cursor = await db.execute(
            "SELECT id FROM rag_chunks WHERE session_id = ?", (session_id,)
        )
        for row in await chunks_cursor.fetchall():
            await db.execute("DELETE FROM rag_chunks_fts WHERE chunk_id = ?", (row["id"],))
        await db.execute("DELETE FROM rag_chunks WHERE session_id = ?", (session_id,))
        await db.execute("DELETE FROM rag_documents WHERE session_id = ?", (session_id,))
        await db.execute("DELETE FROM message_attachments WHERE session_id = ?", (session_id,))
        await db.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
        await db.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
        await db.commit()

    upload_root = Path(settings.UPLOAD_STORAGE_PATH).resolve()
    for raw_path in storage_paths:
        try:
            path = Path(raw_path).resolve()
            if path.is_relative_to(upload_root) and path.is_file():
                path.unlink()
                try:
                    path.parent.rmdir()
                except OSError:
                    pass
        except OSError:
            pass
    return True


async def add_message(
    session_id: str,
    user_id: str,
    role: str,
    content: str,
    conversation_id: str | None = None,
    parent_id: str | None = None,
    status: str = "complete",
    agent_trace: list[dict[str, Any]] | None = None,
    sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    await ensure_session(session_id, user_id)
    message_id = str(uuid4())
    timestamp = _now()

    async with get_db_connection() as db:
        count_cursor = await db.execute(
            "SELECT COUNT(*) AS count FROM chat_messages WHERE session_id = ?",
            (session_id,),
        )
        message_count = int((await count_cursor.fetchone())["count"])

        await db.execute(
            """
            INSERT INTO chat_messages (
                id, session_id, role, content, conversation_id,
                parent_id, status, agent_trace, sources, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                session_id,
                role,
                content,
                conversation_id,
                parent_id,
                status,
                json.dumps(agent_trace or [], ensure_ascii=False),
                json.dumps(sources or [], ensure_ascii=False),
                timestamp,
            ),
        )

        if role == "user" and message_count == 0:
            await db.execute(
                """
                UPDATE chat_sessions
                SET title = ?, updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (_title_from_query(content), timestamp, session_id, user_id),
            )
        else:
            await db.execute(
                """
                UPDATE chat_sessions SET updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (timestamp, session_id, user_id),
            )
        await db.commit()

    return {
        "id": message_id,
        "role": role,
        "content": content,
        "conversation_id": conversation_id,
        "parent_id": parent_id,
        "status": status,
        "agent_trace": agent_trace or [],
        "sources": sources or [],
        "attachments": [],
        "created_at": timestamp,
    }
