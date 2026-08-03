from backend.memory.episode_summary import (
    build_episode_summary,
    improve_legacy_episode,
)


def test_episode_summary_removes_question_sentences_and_internal_enums() -> None:
    summary = build_episode_summary(
        query=(
            "我想系统学习RAG，你还记得我之前问你的有关RA，"
            "大模型如何处理私有知识，减少幻觉，检索增强生成，检索系统，生成模型"
        ),
        concepts=[
            "我想系统学习RAG，你还记得我之前问你的有关RA",
            "大模型如何处理私有知识",
            "减少幻觉",
            "检索增强生成",
            "检索系统",
            "生成模型",
        ],
        activity="explain",
        skill="explain-concept",
    )

    assert summary["primary_concept"] == "RAG"
    assert summary["related_concepts"] == [
        "大模型",
        "私有知识",
        "模型幻觉",
        "检索系统",
    ]
    assert summary["content"] == (
        "本轮学习：RAG；关联概念：大模型、私有知识、模型幻觉、检索系统；"
        "学习方式：概念讲解。"
    )
    assert "explain" not in summary["content"]
    assert "Skill" not in summary["content"]


def test_episode_summary_keeps_clean_concept_hierarchy() -> None:
    summary = build_episode_summary(
        query="给我讲一下什么是马尔可夫链",
        concepts=["马尔可夫链", "无记忆性", "状态空间", "转移概率", "稳态分布"],
        activity="explain",
        skill="explain-concept",
        tools=["query_concept_graph"],
    )
    assert summary["title"] == "马尔可夫链"
    assert summary["activity_label"] == "概念讲解"
    assert summary["tool_labels"] == ["概念图谱"]


def test_legacy_episode_is_improved_on_read_without_losing_metadata() -> None:
    item = {
        "scope": "episodic",
        "kind": "learning_turn",
        "content": "学习了什么是 RAG；活动类型为 explain；使用 Skill explain-concept",
        "metadata": {
            "concepts": ["我想系统学习RAG，什么是检索增强生成", "私有知识", "模型幻觉"],
            "activity": "explain",
            "skill": "explain-concept",
            "tools": [],
        },
    }
    improved = improve_legacy_episode(item)
    assert improved["content"].startswith("本轮学习：RAG；")
    assert improved["metadata"]["primary_concept"] == "RAG"
