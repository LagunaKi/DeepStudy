"""Persistent chat session history API."""

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from backend.data.conversation_store import (
    DEFAULT_SESSION_TITLE,
    create_session,
    delete_session,
    get_session,
    list_sessions,
    rename_session,
)
from backend.data.profile_store import ANONYMOUS_USER_ID

router = APIRouter(prefix="/sessions", tags=["sessions"])


class SessionCreate(BaseModel):
    title: str = Field(DEFAULT_SESSION_TITLE, max_length=80)


class SessionUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=80)


class SessionMessage(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    conversation_id: str | None = None
    parent_id: str | None = None
    status: str
    agent_trace: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str


class SessionSummary(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int


class SessionDetail(SessionSummary):
    messages: list[SessionMessage]


@router.get("", response_model=list[SessionSummary])
async def get_sessions():
    return await list_sessions(ANONYMOUS_USER_ID)


@router.post("", response_model=SessionSummary, status_code=status.HTTP_201_CREATED)
async def post_session(payload: SessionCreate):
    return await create_session(ANONYMOUS_USER_ID, payload.title)


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session_detail(session_id: str):
    session = await get_session(session_id, ANONYMOUS_USER_ID)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session


@router.patch("/{session_id}", response_model=dict[str, str])
async def patch_session(session_id: str, payload: SessionUpdate):
    if not await rename_session(session_id, ANONYMOUS_USER_ID, payload.title):
        raise HTTPException(status_code=404, detail="会话不存在或标题为空")
    return {"id": session_id, "title": payload.title.strip()}


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_session(session_id: str):
    if not await delete_session(session_id, ANONYMOUS_USER_ID):
        raise HTTPException(status_code=404, detail="会话不存在")
