"""SQLite persistence and hybrid retrieval for source-grounded RAG."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from backend.data.sqlite_db import get_db_connection
from backend.rag.chunking import DocumentChunk


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def lexical_terms(text: str) -> list[str]:
    """Build English words plus Chinese unigram/bigram terms for SQLite FTS."""
    normalized = re.sub(r"\s+", " ", text.casefold()).strip()
    latin = re.findall(r"[a-z0-9_]{2,}", normalized)
    chinese_runs = re.findall(r"[\u3400-\u9fff]+", normalized)
    chinese: list[str] = []
    for run in chinese_runs:
        chinese.extend(run)
        chinese.extend(run[index : index + 2] for index in range(len(run) - 1))
    return list(dict.fromkeys([*latin, *chinese]))


def lexical_text(text: str) -> str:
    return " ".join(lexical_terms(text))


async def register_document(
    *,
    user_id: str,
    session_id: str,
    filename: str,
    mime_type: str,
    size_bytes: int,
    content_hash: str,
) -> tuple[dict[str, Any], bool]:
    """Register a document, returning an existing exact duplicate when present."""
    timestamp = _now()
    async with get_db_connection() as db:
        cursor = await db.execute(
            """
            SELECT * FROM rag_documents
            WHERE user_id = ? AND session_id = ? AND filename = ? AND content_hash = ?
            """,
            (user_id, session_id, filename, content_hash),
        )
        existing = await cursor.fetchone()
        if existing is not None:
            return dict(existing), True
        version_cursor = await db.execute(
            """
            SELECT COALESCE(MAX(version), 0) AS version FROM rag_documents
            WHERE user_id = ? AND session_id = ? AND filename = ?
            """,
            (user_id, session_id, filename),
        )
        version = int((await version_cursor.fetchone())["version"]) + 1
        document_id = f"doc_{uuid4().hex}"
        await db.execute(
            """
            INSERT INTO rag_documents (
                id, user_id, session_id, filename, mime_type, size_bytes,
                content_hash, version, status, progress, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued', 5, ?, ?)
            """,
            (
                document_id,
                user_id,
                session_id,
                filename,
                mime_type,
                size_bytes,
                content_hash,
                version,
                timestamp,
                timestamp,
            ),
        )
        await db.commit()
        cursor = await db.execute("SELECT * FROM rag_documents WHERE id = ?", (document_id,))
        return dict(await cursor.fetchone()), False


async def update_document_status(
    document_id: str,
    *,
    status: str,
    progress: int,
    error: str | None = None,
    page_count: int | None = None,
    chunk_count: int | None = None,
) -> None:
    assignments = ["status = ?", "progress = ?", "error = ?", "updated_at = ?"]
    values: list[Any] = [status, max(0, min(100, progress)), error, _now()]
    if page_count is not None:
        assignments.append("page_count = ?")
        values.append(page_count)
    if chunk_count is not None:
        assignments.append("chunk_count = ?")
        values.append(chunk_count)
    values.append(document_id)
    async with get_db_connection() as db:
        await db.execute(
            f"UPDATE rag_documents SET {', '.join(assignments)} WHERE id = ?",
            values,
        )
        await db.execute(
            """
            UPDATE message_attachments
            SET status = ?, progress = ?, error = ?, updated_at = ?
            WHERE document_id = ?
            """,
            (status, max(0, min(100, progress)), error, _now(), document_id),
        )
        await db.commit()


async def replace_chunks(
    document: dict[str, Any],
    chunks: list[DocumentChunk],
    embeddings: list[list[float]],
    embedding_model: str,
) -> None:
    if len(chunks) != len(embeddings):
        raise ValueError("chunk and embedding counts do not match")
    timestamp = _now()
    async with get_db_connection() as db:
        old_cursor = await db.execute(
            "SELECT id FROM rag_chunks WHERE document_id = ?", (document["id"],)
        )
        old_ids = [row["id"] for row in await old_cursor.fetchall()]
        for chunk_id in old_ids:
            await db.execute("DELETE FROM rag_chunks_fts WHERE chunk_id = ?", (chunk_id,))
        await db.execute("DELETE FROM rag_chunks WHERE document_id = ?", (document["id"],))
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            searchable = lexical_text(f"{document['filename']} {chunk.section} {chunk.text}")
            await db.execute(
                """
                INSERT INTO rag_chunks (
                    id, document_id, user_id, session_id, chunk_index, page,
                    section, content, content_hash, lexical_text, embedding,
                    embedding_model, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk.chunk_id,
                    document["id"],
                    document["user_id"],
                    document["session_id"],
                    chunk.chunk_index,
                    chunk.page,
                    chunk.section,
                    chunk.text,
                    chunk.content_hash,
                    searchable,
                    json.dumps(embedding),
                    embedding_model,
                    timestamp,
                ),
            )
            await db.execute(
                "INSERT INTO rag_chunks_fts (chunk_id, content, lexical_text) VALUES (?, ?, ?)",
                (chunk.chunk_id, chunk.text, searchable),
            )
        await db.execute(
            """
            UPDATE rag_documents
            SET status = 'ready', progress = 100, error = NULL,
                chunk_count = ?, updated_at = ?
            WHERE id = ?
            """,
            (len(chunks), timestamp, document["id"]),
        )
        await db.execute(
            """
            UPDATE message_attachments
            SET status = 'ready', progress = 100, error = NULL, updated_at = ?
            WHERE document_id = ?
            """,
            (timestamp, document["id"]),
        )
        await db.commit()


async def get_document(document_id: str, user_id: str = "anonymous") -> dict[str, Any] | None:
    async with get_db_connection() as db:
        cursor = await db.execute(
            "SELECT * FROM rag_documents WHERE id = ? AND user_id = ?",
            (document_id, user_id),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def list_documents(session_id: str, user_id: str = "anonymous") -> list[dict[str, Any]]:
    async with get_db_connection() as db:
        cursor = await db.execute(
            """
            SELECT * FROM rag_documents WHERE session_id = ? AND user_id = ?
            ORDER BY updated_at DESC
            """,
            (session_id, user_id),
        )
        return [dict(row) for row in await cursor.fetchall()]


async def create_attachment(
    *,
    session_id: str,
    document_id: str | None,
    filename: str,
    mime_type: str,
    size_bytes: int,
    status: str,
    progress: int,
    storage_path: str,
) -> dict[str, Any]:
    attachment_id = f"att_{uuid4().hex}"
    timestamp = _now()
    async with get_db_connection() as db:
        await db.execute(
            """
            INSERT INTO message_attachments (
                id, session_id, document_id, filename, mime_type, size_bytes,
                status, progress, storage_path, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                attachment_id,
                session_id,
                document_id,
                filename,
                mime_type,
                size_bytes,
                status,
                progress,
                storage_path,
                timestamp,
                timestamp,
            ),
        )
        await db.commit()
    return {
        "id": attachment_id,
        "session_id": session_id,
        "document_id": document_id,
        "filename": filename,
        "mime_type": mime_type,
        "size_bytes": size_bytes,
        "status": status,
        "progress": progress,
        "error": None,
        "created_at": timestamp,
        "updated_at": timestamp,
    }


async def get_attachments(attachment_ids: list[str], session_id: str) -> list[dict[str, Any]]:
    if not attachment_ids:
        return []
    placeholders = ",".join("?" for _ in attachment_ids)
    async with get_db_connection() as db:
        cursor = await db.execute(
            f"""
            SELECT * FROM message_attachments
            WHERE session_id = ? AND id IN ({placeholders})
            ORDER BY created_at ASC
            """,
            [session_id, *attachment_ids],
        )
        return [dict(row) for row in await cursor.fetchall()]


async def get_document_storage_path(document_id: str, session_id: str) -> str | None:
    async with get_db_connection() as db:
        cursor = await db.execute(
            """
            SELECT storage_path FROM message_attachments
            WHERE document_id = ? AND session_id = ? AND storage_path IS NOT NULL
            ORDER BY created_at ASC LIMIT 1
            """,
            (document_id, session_id),
        )
        row = await cursor.fetchone()
        return str(row["storage_path"]) if row and row["storage_path"] else None


async def link_attachments_to_message(
    attachment_ids: list[str], session_id: str, message_id: str
) -> None:
    if not attachment_ids:
        return
    placeholders = ",".join("?" for _ in attachment_ids)
    async with get_db_connection() as db:
        await db.execute(
            f"""
            UPDATE message_attachments SET message_id = ?, updated_at = ?
            WHERE session_id = ? AND id IN ({placeholders}) AND message_id IS NULL
            """,
            [message_id, _now(), session_id, *attachment_ids],
        )
        await db.commit()


async def lexical_search(
    query: str,
    *,
    user_id: str,
    session_id: str | None,
    document_ids: list[str] | None,
    limit: int,
) -> list[dict[str, Any]]:
    terms = lexical_terms(query)[:24]
    if not terms:
        return []
    match_query = " OR ".join(f'"{term.replace(chr(34), "")}"' for term in terms)
    filters = ["c.user_id = ?", "d.status = 'ready'"]
    values: list[Any] = [match_query, user_id]
    if session_id:
        filters.append("c.session_id = ?")
        values.append(session_id)
    if document_ids:
        filters.append(f"c.document_id IN ({','.join('?' for _ in document_ids)})")
        values.extend(document_ids)
    values.append(limit)
    async with get_db_connection() as db:
        cursor = await db.execute(
            f"""
            SELECT c.*, d.filename, d.version, bm25(rag_chunks_fts) AS rank
            FROM rag_chunks_fts
            JOIN rag_chunks c ON c.id = rag_chunks_fts.chunk_id
            JOIN rag_documents d ON d.id = c.document_id
            WHERE rag_chunks_fts MATCH ? AND {" AND ".join(filters)}
            ORDER BY rank ASC
            LIMIT ?
            """,
            values,
        )
        return [dict(row) for row in await cursor.fetchall()]


async def vector_candidates(
    *,
    user_id: str,
    session_id: str | None,
    document_ids: list[str] | None,
) -> list[dict[str, Any]]:
    filters = ["c.user_id = ?", "d.status = 'ready'", "c.embedding IS NOT NULL"]
    values: list[Any] = [user_id]
    if session_id:
        filters.append("c.session_id = ?")
        values.append(session_id)
    if document_ids:
        filters.append(f"c.document_id IN ({','.join('?' for _ in document_ids)})")
        values.extend(document_ids)
    async with get_db_connection() as db:
        cursor = await db.execute(
            f"""
            SELECT c.*, d.filename, d.version
            FROM rag_chunks c JOIN rag_documents d ON d.id = c.document_id
            WHERE {" AND ".join(filters)}
            """,
            values,
        )
        rows = []
        for row in await cursor.fetchall():
            item = dict(row)
            try:
                item["embedding"] = json.loads(item["embedding"])
            except (json.JSONDecodeError, TypeError):
                continue
            rows.append(item)
        return rows


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return -1.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)
