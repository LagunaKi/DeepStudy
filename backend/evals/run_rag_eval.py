"""Run the checked-in 30-query retrieval baseline without external services."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import tempfile
from pathlib import Path
from typing import Literal

from backend.config import settings
from backend.data import rag_store
from backend.data.rag_store import register_document
from backend.data.sqlite_db import init_db
from backend.rag.embeddings import EmbeddingService
from backend.rag.service import RAGService

RetrieverMode = Literal["bm25", "vector", "hybrid"]


async def evaluate(
    dataset_path: Path,
    corpus_path: Path,
    *,
    retriever: RetrieverMode = "hybrid",
) -> dict[str, float | int]:
    cases = json.loads(dataset_path.read_text())
    payload = corpus_path.read_bytes()
    with tempfile.TemporaryDirectory(prefix="deepstudy-rag-eval-") as temp_dir:
        settings.SQLITE_DB_PATH = str(Path(temp_dir) / "eval.db")
        await init_db()
        document, _ = await register_document(
            user_id="anonymous",
            session_id="evaluation",
            filename=corpus_path.name,
            mime_type="text/markdown",
            size_bytes=len(payload),
            content_hash=hashlib.sha256(payload).hexdigest(),
        )
        embeddings = EmbeddingService()
        embeddings._model_failed = True
        service = RAGService(embeddings=embeddings, enable_graph=False)
        await service.ingest(document["id"], str(corpus_path))

        hits = 0
        reciprocal_ranks: list[float] = []
        ndcgs: list[float] = []
        for case in cases:
            if retriever == "bm25":
                results = await rag_store.lexical_search(
                    case["query"],
                    user_id="anonymous",
                    session_id="evaluation",
                    document_ids=None,
                    limit=5,
                )
            elif retriever == "vector":
                vector_rows = await rag_store.vector_candidates(
                    user_id="anonymous",
                    session_id="evaluation",
                    document_ids=None,
                )
                query_vector = embeddings.embed_query(case["query"])
                results = [
                    row
                    for _, row in sorted(
                        (
                            (rag_store.cosine_similarity(query_vector, row["embedding"]), row)
                            for row in vector_rows
                        ),
                        key=lambda item: item[0],
                        reverse=True,
                    )[:5]
                ]
            else:
                results = await service.search(
                    case["query"],
                    user_id="anonymous",
                    session_id="evaluation",
                    top_k=5,
                )
            relevant = set(case["relevant_sections"])
            relevance = [1 if item["section"] in relevant else 0 for item in results]
            first = next((index for index, value in enumerate(relevance, start=1) if value), None)
            hits += int(first is not None)
            reciprocal_ranks.append(1 / first if first else 0.0)
            dcg = sum(
                value / math.log2(index + 1)
                for index, value in enumerate(relevance, start=1)
            )
            ideal_count = min(len(relevant), 5)
            ideal = sum(1 / math.log2(index + 1) for index in range(1, ideal_count + 1))
            ndcgs.append(dcg / ideal if ideal else 0.0)

    count = len(cases)
    return {
        "queries": count,
        "recall_at_5": round(hits / count, 4),
        "mrr": round(sum(reciprocal_ranks) / count, 4),
        "ndcg_at_5": round(sum(ndcgs) / count, 4),
    }


def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=root / "rag_cases.json")
    parser.add_argument("--corpus", type=Path, default=root / "course_fixture.md")
    parser.add_argument(
        "--retriever",
        choices=("bm25", "vector", "hybrid"),
        default="hybrid",
        help="Evaluate one retrieval strategy (default: hybrid).",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Print a reproducible legacy vector-only versus hybrid comparison.",
    )
    args = parser.parse_args()
    if args.compare:
        vector = asyncio.run(evaluate(args.dataset, args.corpus, retriever="vector"))
        hybrid = asyncio.run(evaluate(args.dataset, args.corpus, retriever="hybrid"))
        comparison = {
            "legacy_vector_only": vector,
            "hybrid_rrf_rerank": hybrid,
            "delta": {
                key: round(float(hybrid[key]) - float(vector[key]), 4)
                for key in ("recall_at_5", "mrr", "ndcg_at_5")
            },
        }
        print(json.dumps(comparison, indent=2))
        return
    result = asyncio.run(evaluate(args.dataset, args.corpus, retriever=args.retriever))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
