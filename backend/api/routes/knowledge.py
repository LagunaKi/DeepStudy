"""Course-material upload, processing status, retrieval, and source access APIs."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.api.schemas.response import MindMapGraph
from backend.config import settings
from backend.data.conversation_store import ensure_session
from backend.data.neo4j_client import neo4j_client
from backend.data.profile_store import ANONYMOUS_USER_ID
from backend.data.rag_store import (
    create_attachment,
    get_document,
    get_document_storage_path,
    list_documents,
    register_document,
    update_document_status,
)
from backend.rag.chunking import (
    SUPPORTED_EXTENSIONS,
    content_hash,
    file_kind,
    safe_filename,
)
from backend.rag.service import rag_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class SearchQuery(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    session_id: str | None = None
    document_ids: list[str] | None = None
    top_k: int = Field(5, ge=1, le=10)


def _public_document(document: dict[str, Any]) -> dict[str, Any]:
    return {
        key: document.get(key)
        for key in (
            "id",
            "session_id",
            "filename",
            "mime_type",
            "size_bytes",
            "version",
            "status",
            "progress",
            "error",
            "page_count",
            "chunk_count",
            "created_at",
            "updated_at",
        )
    }


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_file(
    background_tasks: BackgroundTasks,
    session_id: str = Form(...),
    file: UploadFile = File(...),  # noqa: B008 - FastAPI declares uploads via defaults
):
    filename = safe_filename(file.filename or "upload")
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise HTTPException(status_code=415, detail=f"不支持该文件格式。支持：{supported}")
    payload = await file.read(settings.RAG_MAX_FILE_BYTES + 1)
    if len(payload) > settings.RAG_MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"文件不能超过 {settings.RAG_MAX_FILE_BYTES // (1024 * 1024)} MB",
        )
    if not payload:
        raise HTTPException(status_code=400, detail="文件内容为空")

    await ensure_session(session_id, ANONYMOUS_USER_ID)
    upload_root = Path(settings.UPLOAD_STORAGE_PATH).resolve()
    upload_root.mkdir(parents=True, exist_ok=True)
    mime_type = file.content_type or "application/octet-stream"

    if file_kind(filename) == "image":
        if len(payload) > settings.RAG_MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"图片不能超过 {settings.RAG_MAX_IMAGE_BYTES // (1024 * 1024)} MB",
            )
        session_key = content_hash(session_id.encode())[:16]
        image_dir = upload_root / f"session-{session_key}"
        image_dir.mkdir(parents=True, exist_ok=True)
        storage_path = image_dir / f"{content_hash(payload)[:16]}-{filename}"
        await asyncio.to_thread(storage_path.write_bytes, payload)
        attachment = await create_attachment(
            session_id=session_id,
            document_id=None,
            filename=filename,
            mime_type=mime_type,
            size_bytes=len(payload),
            status="ready",
            progress=100,
            storage_path=str(storage_path),
        )
        return {"attachment": attachment, "document": None, "deduplicated": False}

    document, duplicate = await register_document(
        user_id=ANONYMOUS_USER_ID,
        session_id=session_id,
        filename=filename,
        mime_type=mime_type,
        size_bytes=len(payload),
        content_hash=content_hash(payload),
    )
    document_dir = upload_root / document["id"]
    document_dir.mkdir(parents=True, exist_ok=True)
    storage_path = document_dir / filename
    should_ingest = not duplicate or document["status"] == "failed"
    if should_ingest:
        await asyncio.to_thread(storage_path.write_bytes, payload)
        if duplicate:
            await update_document_status(
                document["id"], status="queued", progress=5, error=None
            )
            document.update({"status": "queued", "progress": 5, "error": None})
    attachment = await create_attachment(
        session_id=session_id,
        document_id=document["id"],
        filename=filename,
        mime_type=mime_type,
        size_bytes=len(payload),
        status=document["status"],
        progress=int(document["progress"]),
        storage_path=str(storage_path) if storage_path.exists() else "",
    )
    if should_ingest:
        background_tasks.add_task(rag_service.ingest, document["id"], str(storage_path))
    return {
        "attachment": attachment,
        "document": _public_document(document),
        "deduplicated": duplicate,
    }


@router.get("/documents")
async def get_documents(session_id: str):
    return [_public_document(item) for item in await list_documents(session_id)]


@router.get("/documents/{document_id}")
async def get_document_status(document_id: str):
    document = await get_document(document_id, ANONYMOUS_USER_ID)
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")
    return _public_document(document)


@router.get("/documents/{document_id}/content")
async def get_document_content(document_id: str):
    document = await get_document(document_id, ANONYMOUS_USER_ID)
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")
    storage_path = await get_document_storage_path(document_id, document["session_id"])
    if not storage_path or not Path(storage_path).is_file():
        raise HTTPException(status_code=404, detail="原始文件不可用")
    return FileResponse(
        storage_path,
        media_type=document["mime_type"],
        filename=document["filename"],
        content_disposition_type="inline",
    )


@router.post("/search")
async def search_knowledge(payload: SearchQuery):
    items = await rag_service.search(
        payload.query,
        user_id=ANONYMOUS_USER_ID,
        session_id=payload.session_id,
        document_ids=payload.document_ids,
        top_k=payload.top_k,
    )
    return {"query": payload.query, "count": len(items), "items": items}


@router.get("/graph", response_model=MindMapGraph)
async def get_knowledge_graph(session_id: str):
    """Return the source domain graph, separate from the dialogue learning map."""
    try:
        records = await neo4j_client.query(
            """
            MATCH (d:Document {user_id: $user_id, session_id: $session_id})
            OPTIONAL MATCH (c:Chunk)-[:PART_OF]->(d)
            OPTIONAL MATCH (c)-[:MENTIONS]->(concept:Concept)
            RETURN d.document_id AS document_id, d.filename AS filename,
                   c.chunk_id AS chunk_id, c.section AS section,
                   concept.name AS concept
            ORDER BY d.filename, c.chunk_index
            LIMIT 160
            """,
            {"user_id": ANONYMOUS_USER_ID, "session_id": session_id},
        )
    except Exception:
        return MindMapGraph(nodes=[], edges=[])
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[str, dict[str, Any]] = {}
    for record in records:
        document_id = record.get("document_id")
        chunk_id = record.get("chunk_id")
        concept = record.get("concept")
        if document_id:
            nodes[document_id] = {
                "id": document_id,
                "data": {"label": record.get("filename") or "课程资料", "type": "document"},
                "position": {"x": 0, "y": 0},
            }
        if chunk_id:
            nodes[chunk_id] = {
                "id": chunk_id,
                "data": {"label": record.get("section") or "文档片段", "type": "chunk"},
                "position": {"x": 0, "y": 0},
            }
            edge_id = f"{document_id}-contains-{chunk_id}"
            edges[edge_id] = {
                "id": edge_id,
                "source": document_id,
                "target": chunk_id,
                "label": "HAS_CHUNK",
            }
        if chunk_id and concept:
            concept_id = f"concept:{concept}"
            nodes[concept_id] = {
                "id": concept_id,
                "data": {"label": concept, "type": "concept"},
                "position": {"x": 0, "y": 0},
            }
            edge_id = f"{chunk_id}-mentions-{concept_id}"
            edges[edge_id] = {
                "id": edge_id,
                "source": chunk_id,
                "target": concept_id,
                "label": "MENTIONS",
            }
    return MindMapGraph(nodes=list(nodes.values()), edges=list(edges.values()))
