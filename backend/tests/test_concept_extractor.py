from backend.agent.concept_extractor import extract_concept_structure


def test_extract_concepts_from_query_and_markdown_answer() -> None:
    result = extract_concept_structure(
        "给我讲一下什么是马尔可夫链",
        """### 1. 通俗易懂的解释：什么是马尔可夫链？
**无记忆性**是核心。它包含**状态空间（State Space）**和
**转移概率（Transition Probability）**。最后是**稳态分布**。
""",
    )

    assert result["root"] == "马尔可夫链"
    assert result["children"] == ["无记忆性", "状态空间", "转移概率", "稳态分布"]


def test_extract_concepts_deduplicates_and_limits_children() -> None:
    result = extract_concept_structure(
        "仔细讲解这个 RAG",
        " ".join(f"**概念{i}**" for i in range(8)) + " **概念1**",
    )

    assert result["root"] == "RAG"
    assert result["children"] == ["概念0", "概念1", "概念2", "概念3", "概念4"]
