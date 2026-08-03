"""长期记忆查看、确认、编辑与遗忘 API。"""

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from backend.memory.service import memory_service

ANONYMOUS_USER_ID = "anonymous"
router = APIRouter(prefix="/memories", tags=["memories"])


class MemoryCreate(BaseModel):
    content: str = Field(min_length=1, max_length=1200)
    kind: str = Field(default="user_note", min_length=1, max_length=40)
    importance: float = Field(default=0.9, ge=0, le=1)


class MemoryUpdate(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=1200)
    user_confirmed: bool | None = None
    importance: float | None = Field(default=None, ge=0, le=1)


@router.get("")
async def list_memories(
    scope: Literal["semantic", "episodic"] | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> list[dict[str, Any]]:
    return await memory_service.list(
        user_id=ANONYMOUS_USER_ID, scope=scope, limit=limit
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_memory(body: MemoryCreate) -> dict[str, Any]:
    memory, created = await memory_service.upsert(
        user_id=ANONYMOUS_USER_ID,
        scope="semantic",
        kind=body.kind,
        content=body.content,
        source="user",
        confidence=1.0,
        importance=body.importance,
        user_confirmed=True,
    )
    return {"memory": memory, "created": created}


@router.patch("/{memory_id}")
async def update_memory(memory_id: str, body: MemoryUpdate) -> dict[str, Any]:
    memory = await memory_service.update(
        memory_id,
        user_id=ANONYMOUS_USER_ID,
        content=body.content,
        user_confirmed=body.user_confirmed,
        importance=body.importance,
    )
    if not memory:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return memory


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(memory_id: str) -> None:
    deleted = await memory_service.delete(memory_id, user_id=ANONYMOUS_USER_ID)
    if not deleted:
        raise HTTPException(status_code=404, detail="记忆不存在")
