"""High-level ingestion, hybrid retrieval, reranking, and citation formatting."""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any

from backend.data import rag_store
from backend.data.neo4j_client import neo4j_client
from backend.rag.chunking import chunk_document, parse_document
from backend.rag.embeddings import EmbeddingService, embedding_service

logger = logging.getLogger(__name__)
RRF_K = 60
LEXICAL_RRF_WEIGHT = 1.5
DENSE_RRF_WEIGHT = 1.0
GRAPH_RRF_WEIGHT = 0.7


class RAGService:
    def __init__(
        self,
        embeddings: EmbeddingService | None = None,
        *,
        enable_graph: bool = True,
    ) -> None:
        self.embeddings = embeddings or embedding_service
        self.enable_graph = enable_graph

    async def ingest(self, document_id: str, storage_path: str) -> None:
        document = await rag_store.get_document(document_id)
        if not document:
            return
        try:
            await rag_store.update_document_status(document_id, status="parsing", progress=20)
            payload = await asyncio.to_thread(Path(storage_path).read_bytes)
            parsed = await asyncio.to_thread(parse_document, document["filename"], payload)
            chunks = chunk_document(document_id, int(document["version"]), parsed)
            if not chunks:
                raise ValueError("文档解析成功，但没有生成可检索片段")
            await rag_store.update_document_status(
                document_id,
                status="embedding",
                progress=55,
                page_count=parsed.page_count,
                chunk_count=len(chunks),
            )
            vectors = await asyncio.to_thread(
                self.embeddings.embed_batch, [chunk.text for chunk in chunks]
            )
            await rag_store.update_document_status(document_id, status="indexing", progress=85)
            await rag_store.replace_chunks(
                document,
                chunks,
                vectors,
                self.embeddings.active_model,
            )
            try:
                if not self.enable_graph:
                    return
                await asyncio.wait_for(
                    neo4j_client.upsert_rag_document(document, chunks), timeout=5
                )
            except Exception as exc:
                logger.warning(
                    "GraphRAG indexing unavailable; vector/keyword index remains ready: %s",
                    exc,
                )
        except Exception as exc:
            message = str(exc)[:500] or "文档处理失败"
            logger.warning("RAG ingestion failed: document=%s error=%s", document_id, message)
            await rag_store.update_document_status(
                document_id, status="failed", progress=100, error=message
            )

    async def search(
        self,
        query: str,
        *,
        user_id: str = "anonymous",
        session_id: str | None = None,
        document_ids: list[str] | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Fuse BM25, dense and graph ranks, then deterministically rerank."""
        pool_size = max(top_k * 4, 12)
        lexical_task = rag_store.lexical_search(
            query,
            user_id=user_id,
            session_id=session_id,
            document_ids=document_ids,
            limit=pool_size,
        )
        vector_rows_task = rag_store.vector_candidates(
            user_id=user_id,
            session_id=session_id,
            document_ids=document_ids,
        )
        lexical, vector_rows = await asyncio.gather(lexical_task, vector_rows_task)

        if not lexical and not vector_rows:
            return []

        query_vector = await asyncio.to_thread(self.embeddings.embed_query, query)
        dense = sorted(
            (
                (rag_store.cosine_similarity(query_vector, row["embedding"]), row)
                for row in vector_rows
            ),
            key=lambda item: item[0],
            reverse=True,
        )[:pool_size]

        graph_ids: list[str] = []
        if self.enable_graph:
            try:
                graph_ids = await asyncio.wait_for(
                    neo4j_client.search_rag_chunk_ids(
                        rag_store.lexical_terms(query)[:8],
                        user_id=user_id,
                        session_id=session_id,
                        limit=pool_size,
                    ),
                    timeout=2,
                )
            except Exception:
                pass

        fused: dict[str, dict[str, Any]] = {}
        for rank, row in enumerate(lexical, start=1):
            item = fused.setdefault(row["id"], {"row": row, "score": 0.0, "signals": {}})
            # Course questions often contain exact theorem names or symbols. Give the
            # lexical signal a modest lead while retaining dense recall for paraphrases.
            item["score"] += LEXICAL_RRF_WEIGHT / (RRF_K + rank)
            item["signals"]["bm25_rank"] = rank
        for rank, (similarity, row) in enumerate(dense, start=1):
            item = fused.setdefault(row["id"], {"row": row, "score": 0.0, "signals": {}})
            item["score"] += DENSE_RRF_WEIGHT / (RRF_K + rank)
            item["signals"]["vector_rank"] = rank
            item["signals"]["vector_score"] = round(similarity, 4)
        for rank, chunk_id in enumerate(graph_ids, start=1):
            if chunk_id in fused:
                fused[chunk_id]["score"] += GRAPH_RRF_WEIGHT / (RRF_K + rank)
                fused[chunk_id]["signals"]["graph_rank"] = rank

        query_terms = set(rag_store.lexical_terms(query))
        for item in fused.values():
            row = item["row"]
            candidate_terms = set(rag_store.lexical_terms(f"{row['section']} {row['content']}"))
            coverage = len(query_terms & candidate_terms) / max(1, len(query_terms))
            section_match = any(term in str(row["section"]).casefold() for term in query_terms)
            item["score"] += coverage * 0.04 + (0.015 if section_match else 0.0)
            item["signals"]["term_coverage"] = round(coverage, 4)

        ranked = sorted(fused.values(), key=lambda item: (-item["score"], item["row"]["id"]))
        selected: list[dict[str, Any]] = []
        per_document: dict[str, int] = {}
        for item in ranked:
            row = item["row"]
            if per_document.get(row["document_id"], 0) >= 3:
                continue
            per_document[row["document_id"]] = per_document.get(row["document_id"], 0) + 1
            content = re.sub(r"\s+", " ", row["content"]).strip()
            selected.append(
                {
                    "citation": len(selected) + 1,
                    "document_id": row["document_id"],
                    "chunk_id": row["id"],
                    "filename": row["filename"],
                    "version": row["version"],
                    "page": row["page"],
                    "section": row["section"],
                    "text": row["content"],
                    "snippet": content[:360] + ("…" if len(content) > 360 else ""),
                    "score": round(item["score"], 6),
                    "signals": item["signals"],
                }
            )
            if len(selected) >= top_k:
                break
        return selected

    @staticmethod
    def evidence_prompt(items: list[dict[str, Any]]) -> str:
        items = [item for item in items if "citation" in item and "filename" in item]
        if not items:
            return ""
        blocks = []
        for item in items:
            location = item["filename"]
            if item.get("page"):
                location += f"，第 {item['page']} 页"
            if item.get("section"):
                location += f"，{item['section']}"
            blocks.append(f"[{item['citation']}] {location}\n{item['text']}")
        return "\n\n".join(blocks)


rag_service = RAGService()
