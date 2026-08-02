"""Run the checked-in 30-query retrieval baseline without external services."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import tempfile
from pathlib import Path

from backend.config import settings
from backend.data.rag_store import register_document
from backend.data.sqlite_db import init_db
from backend.rag.embeddings import EmbeddingService
from backend.rag.service import RAGService


async def evaluate(dataset_path: Path, corpus_path: Path) -> dict[str, float | int]:
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
    args = parser.parse_args()
    print(json.dumps(asyncio.run(evaluate(args.dataset, args.corpus)), indent=2))


if __name__ == "__main__":
    main()
