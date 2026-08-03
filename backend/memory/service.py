"""可检索、可去重、可编辑和可遗忘的长期记忆服务。"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from backend.data.rag_store import lexical_terms
from backend.data.sqlite_db import get_db_connection
from backend.memory.episode_summary import improve_legacy_episode


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize(content: str) -> str:
    return re.sub(r"\s+", " ", content).strip().casefold()


def _dedupe_key(
    scope: str,
    kind: str,
    content: str,
    episode_identity: str | None = None,
) -> str:
    identity = f":{episode_identity}" if scope == "episodic" and episode_identity else ""
    payload = f"{scope}:{kind}:{_normalize(content)}{identity}".encode()
    return hashlib.sha256(payload).hexdigest()


def _decode(row: Any) -> dict[str, Any]:
    item = dict(row)
    item["user_confirmed"] = bool(item["user_confirmed"])
    try:
        item["metadata"] = json.loads(item.get("metadata") or "{}")
    except json.JSONDecodeError:
        item["metadata"] = {}
    return item


class MemoryService:
    """管理 semantic facts 与 episodic learning events。"""

    async def upsert(
        self,
        *,
        user_id: str,
        scope: str,
        kind: str,
        content: str,
        source: str,
        source_session_id: str | None = None,
        source_conversation_id: str | None = None,
        confidence: float = 0.7,
        importance: float = 0.5,
        user_confirmed: bool = False,
        metadata: dict[str, Any] | None = None,
        expires_at: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        content = re.sub(r"\s+", " ", content).strip()[:1200]
        if scope not in {"semantic", "episodic"}:
            raise ValueError("scope must be semantic or episodic")
        if not content:
            raise ValueError("memory content must not be empty")
        normalized = _normalize(content)
        key = _dedupe_key(scope, kind, content, source_conversation_id)
        timestamp = _now()
        memory_id = f"mem_{uuid4().hex}"
        async with get_db_connection() as db:
            cursor = await db.execute(
                "SELECT id FROM agent_memories WHERE user_id = ? AND dedupe_key = ?",
                (user_id, key),
            )
            existing = await cursor.fetchone()
            created = existing is None
            if created:
                await db.execute(
                    """
                    INSERT INTO agent_memories (
                        id, user_id, scope, kind, content, normalized_content,
                        dedupe_key, source, source_session_id, source_conversation_id,
                        confidence, importance, user_confirmed, expires_at, metadata,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        memory_id, user_id, scope, kind, content, normalized, key,
                        source, source_session_id, source_conversation_id,
                        max(0.0, min(1.0, confidence)),
                        max(0.0, min(1.0, importance)), int(user_confirmed), expires_at,
                        json.dumps(metadata or {}, ensure_ascii=False), timestamp, timestamp,
                    ),
                )
                action = "create"
            else:
                memory_id = str(existing["id"])
                await db.execute(
                    """
                    UPDATE agent_memories
                    SET confidence = MAX(confidence, ?),
                        importance = MAX(importance, ?),
                        user_confirmed = MAX(user_confirmed, ?),
                        source_session_id = COALESCE(?, source_session_id),
                        source_conversation_id = COALESCE(?, source_conversation_id),
                        metadata = ?, updated_at = ?
                    WHERE id = ? AND user_id = ?
                    """,
                    (
                        confidence, importance, int(user_confirmed), source_session_id,
                        source_conversation_id, json.dumps(metadata or {}, ensure_ascii=False),
                        timestamp, memory_id, user_id,
                    ),
                )
                action = "dedupe_refresh"
            await self._audit(db, memory_id, user_id, action, {"scope": scope, "kind": kind})
            await db.commit()
            cursor = await db.execute(
                "SELECT * FROM agent_memories WHERE id = ? AND user_id = ?",
                (memory_id, user_id),
            )
            return _decode(await cursor.fetchone()), created

    async def list(
        self,
        *,
        user_id: str,
        scope: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        filters = ["user_id = ?", "(expires_at IS NULL OR expires_at > ?)"]
        values: list[Any] = [user_id, _now()]
        if scope:
            filters.append("scope = ?")
            values.append(scope)
        values.append(max(1, min(500, limit)))
        async with get_db_connection() as db:
            cursor = await db.execute(
                f"""
                SELECT * FROM agent_memories
                WHERE {' AND '.join(filters)}
                ORDER BY user_confirmed DESC, importance DESC, updated_at DESC
                LIMIT ?
                """,
                values,
            )
            return [improve_legacy_episode(_decode(row)) for row in await cursor.fetchall()]

    async def retrieve(
        self,
        query: str,
        *,
        user_id: str,
        current_session_id: str | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """本地混合打分：词项覆盖 + 置信度 + 重要度 + 时间衰减。"""
        memories = await self.list(user_id=user_id, limit=300)
        query_terms = set(lexical_terms(query))
        now = datetime.now(timezone.utc)
        ranked: list[tuple[float, dict[str, Any]]] = []
        for item in memories:
            memory_terms = set(lexical_terms(item["content"]))
            overlap = len(query_terms & memory_terms) / max(1, len(query_terms))
            exact = 1.0 if item["normalized_content"] in _normalize(query) else 0.0
            created = datetime.fromisoformat(item["updated_at"])
            age_days = max(0.0, (now - created).total_seconds() / 86400)
            recency = math.exp(-age_days / 120)
            cross_session = bool(
                current_session_id
                and item.get("source_session_id")
                and item["source_session_id"] != current_session_id
            )
            score = (
                overlap * 0.5
                + exact * 0.15
                + float(item["confidence"]) * 0.1
                + float(item["importance"]) * 0.12
                + recency * 0.08
                + (0.08 if item["user_confirmed"] else 0.0)
                + (0.03 if cross_session else 0.0)
            )
            # 无词项命中时只允许用户明确确认的高重要语义偏好进入上下文。
            if overlap == 0 and not (
                item["scope"] == "semantic"
                and item["user_confirmed"]
                and float(item["importance"]) >= 0.8
            ):
                continue
            ranked.append((score, item))
        selected = [item | {"retrieval_score": round(score, 4)} for score, item in sorted(
            ranked, key=lambda pair: (-pair[0], pair[1]["id"])
        )[: max(1, min(12, top_k))]]
        if selected:
            timestamp = _now()
            async with get_db_connection() as db:
                for item in selected:
                    await db.execute(
                        """
                        UPDATE agent_memories
                        SET access_count = access_count + 1, last_accessed_at = ?
                        WHERE id = ? AND user_id = ?
                        """,
                        (timestamp, item["id"], user_id),
                    )
                await db.commit()
        return selected

    async def update(
        self,
        memory_id: str,
        *,
        user_id: str,
        content: str | None = None,
        user_confirmed: bool | None = None,
        importance: float | None = None,
    ) -> dict[str, Any] | None:
        async with get_db_connection() as db:
            cursor = await db.execute(
                "SELECT * FROM agent_memories WHERE id = ? AND user_id = ?",
                (memory_id, user_id),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            old = _decode(row)
            next_content = (
                re.sub(r"\s+", " ", content).strip()[:1200]
                if content
                else old["content"]
            )
            next_confirmed = old["user_confirmed"] if user_confirmed is None else user_confirmed
            next_importance = (
                old["importance"]
                if importance is None
                else max(0.0, min(1.0, importance))
            )
            next_key = _dedupe_key(
                old["scope"],
                old["kind"],
                next_content,
                old.get("source_conversation_id"),
            )
            duplicate_cursor = await db.execute(
                """
                SELECT id FROM agent_memories
                WHERE user_id = ? AND dedupe_key = ? AND id != ?
                """,
                (user_id, next_key, memory_id),
            )
            duplicate = await duplicate_cursor.fetchone()
            if duplicate:
                target_id = str(duplicate["id"])
                await db.execute(
                    """
                    UPDATE agent_memories
                    SET user_confirmed = MAX(user_confirmed, ?),
                        importance = MAX(importance, ?), updated_at = ?
                    WHERE id = ? AND user_id = ?
                    """,
                    (int(next_confirmed), next_importance, _now(), target_id, user_id),
                )
                await db.execute(
                    "DELETE FROM agent_memories WHERE id = ? AND user_id = ?",
                    (memory_id, user_id),
                )
                await self._audit(
                    db, memory_id, user_id, "merge", {"target_memory_id": target_id}
                )
                await db.commit()
                cursor = await db.execute(
                    "SELECT * FROM agent_memories WHERE id = ?", (target_id,)
                )
                return _decode(await cursor.fetchone())
            await db.execute(
                """
                UPDATE agent_memories SET content = ?, normalized_content = ?, dedupe_key = ?,
                    user_confirmed = ?, importance = ?, updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (
                    next_content, _normalize(next_content),
                    next_key,
                    int(next_confirmed), next_importance, _now(), memory_id, user_id,
                ),
            )
            await self._audit(db, memory_id, user_id, "update", {"edited": content is not None})
            await db.commit()
            cursor = await db.execute(
                "SELECT * FROM agent_memories WHERE id = ?", (memory_id,)
            )
            return _decode(await cursor.fetchone())

    async def delete(self, memory_id: str, *, user_id: str) -> bool:
        """永久删除正文，仅保留不含正文的删除审计记录。"""
        async with get_db_connection() as db:
            cursor = await db.execute(
                "SELECT scope, kind FROM agent_memories WHERE id = ? AND user_id = ?",
                (memory_id, user_id),
            )
            row = await cursor.fetchone()
            if not row:
                return False
            await db.execute(
                "DELETE FROM agent_memories WHERE id = ? AND user_id = ?",
                (memory_id, user_id),
            )
            await self._audit(
                db, memory_id, user_id, "delete",
                {"scope": row["scope"], "kind": row["kind"]},
            )
            await db.commit()
            return True

    async def extract_semantic_candidates(self, query: str) -> list[dict[str, Any]]:
        """仅提取用户明确陈述的稳定事实，避免把普通问题误记为偏好。"""
        text = re.sub(r"\s+", " ", query).strip()
        candidates: list[dict[str, Any]] = []
        patterns = (
            (r"(?:请记住|记住)[：,:， ]*(.{2,160})", "explicit", 0.98, 0.95, True),
            (r"(?:我的目标是|我想要|我希望)[：,:， ]*(.{2,120})", "goal", 0.88, 0.85, False),
            (r"(?:我喜欢|我偏好)[：,:， ]*(.{2,100})", "preference", 0.9, 0.75, False),
            (r"(?:我不喜欢|不要给我)[：,:， ]*(.{2,100})", "preference", 0.9, 0.8, False),
            (
                r"(?:我的基础|我不太会|我不擅长)[：,:， ]*(.{2,100})",
                "background", 0.82, 0.75, False,
            ),
        )
        for pattern, kind, confidence, importance, confirmed in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue
            fact = match.group(0).rstrip("。！？!?；;")
            if 4 <= len(fact) <= 180:
                candidates.append({
                    "kind": kind,
                    "content": fact,
                    "confidence": confidence,
                    "importance": importance,
                    "user_confirmed": confirmed,
                })
                if kind == "explicit":
                    return candidates
        return candidates[:3]

    @staticmethod
    async def _audit(
        db: Any,
        memory_id: str,
        user_id: str,
        action: str,
        details: dict[str, Any],
    ) -> None:
        await db.execute(
            """
            INSERT INTO agent_memory_audit (id, memory_id, user_id, action, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                f"audit_{uuid4().hex}", memory_id, user_id, action,
                json.dumps(details, ensure_ascii=False), _now(),
            ),
        )


memory_service = MemoryService()
