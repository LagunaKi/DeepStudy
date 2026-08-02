import asyncio
import hashlib
import io
from pathlib import Path

from fastapi import BackgroundTasks
from starlette.datastructures import Headers, UploadFile

from backend.api.routes import knowledge as knowledge_route
from backend.config import settings
from backend.data.rag_store import get_document, list_documents, register_document
from backend.data.sqlite_db import init_db
from backend.rag.chunking import chunk_document, parse_document
from backend.rag.service import RAGService


class FakeEmbeddings:
    active_model = "fake-test-v1"

    @staticmethod
    def _embed(text: str) -> list[float]:
        normalized = text.casefold()
        return [
            float(normalized.count("梯度") + normalized.count("gradient")),
            float(normalized.count("注意力") + normalized.count("attention")),
            1.0,
        ]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


def test_markdown_chunking_preserves_section_provenance() -> None:
    parsed = parse_document(
        "lesson.md",
        b"# Neural Networks\n\nOverview.\n\n## Backpropagation\n\nGradient details.",
    )
    chunks = chunk_document("doc-test", 1, parsed, target_chars=80, overlap_chars=10)

    assert [section.section for section in parsed.sections] == [
        "Neural Networks",
        "Neural Networks / Backpropagation",
    ]
    assert chunks[1].section.endswith("Backpropagation")
    assert chunks[0].chunk_id.startswith("chk_")


def test_ingestion_dedup_version_and_hybrid_retrieval(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "SQLITE_DB_PATH", str(tmp_path / "rag.db"))

    service = RAGService(embeddings=FakeEmbeddings(), enable_graph=False)

    async def scenario() -> None:
        await init_db()
        payload = (
            "# 深度学习\n\n## 反向传播\n\n反向传播使用链式法则计算梯度。\n\n"
            "## 注意力\n\n注意力机制根据查询和键计算权重。"
        ).encode()
        digest = hashlib.sha256(payload).hexdigest()
        document, duplicate = await register_document(
            user_id="anonymous",
            session_id="rag-session",
            filename="lesson.md",
            mime_type="text/markdown",
            size_bytes=len(payload),
            content_hash=digest,
        )
        assert duplicate is False
        path = Path(tmp_path / "lesson.md")
        path.write_bytes(payload)
        await service.ingest(document["id"], str(path))

        duplicate_document, duplicate = await register_document(
            user_id="anonymous",
            session_id="rag-session",
            filename="lesson.md",
            mime_type="text/markdown",
            size_bytes=len(payload),
            content_hash=digest,
        )
        assert duplicate is True
        assert duplicate_document["id"] == document["id"]

        revised = payload + "\n新增内容".encode()
        revised_document, duplicate = await register_document(
            user_id="anonymous",
            session_id="rag-session",
            filename="lesson.md",
            mime_type="text/markdown",
            size_bytes=len(revised),
            content_hash=hashlib.sha256(revised).hexdigest(),
        )
        assert duplicate is False
        assert revised_document["version"] == 2

        results = await service.search(
            "链式法则如何计算梯度？",
            user_id="anonymous",
            session_id="rag-session",
            top_k=3,
        )
        assert results
        assert results[0]["filename"] == "lesson.md"
        assert "反向传播" in results[0]["section"]
        assert results[0]["citation"] == 1
        assert {"bm25_rank", "vector_rank"} & set(results[0]["signals"])

        documents = await list_documents("rag-session")
        assert {item["version"] for item in documents} == {1, 2}

    asyncio.run(scenario())


def test_upload_api_runs_document_through_background_ingestion(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "SQLITE_DB_PATH", str(tmp_path / "upload.db"))
    monkeypatch.setattr(settings, "UPLOAD_STORAGE_PATH", str(tmp_path / "uploads"))
    monkeypatch.setattr(
        knowledge_route,
        "rag_service",
        RAGService(embeddings=FakeEmbeddings(), enable_graph=False),
    )

    async def scenario() -> None:
        await init_db()
        background = BackgroundTasks()
        upload = UploadFile(
            file=io.BytesIO(b"# RAG\n\nRetrieval augmented generation uses evidence."),
            filename="rag.md",
            headers=Headers({"content-type": "text/markdown"}),
        )
        response = await knowledge_route.upload_file(
            background,
            session_id="upload-session",
            file=upload,
        )
        assert response["attachment"]["status"] == "queued"
        await background()
        document = await get_document(response["document"]["id"])
        assert document is not None
        assert document["status"] == "ready"
        assert document["chunk_count"] == 1

    asyncio.run(scenario())
