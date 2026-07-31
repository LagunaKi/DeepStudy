from backend.agent.extractors import knowledge_extractor


def test_extracts_and_deduplicates_chinese_triples() -> None:
    text = "人工智能是计算机科学的分支。机器学习属于人工智能。"

    triples = knowledge_extractor.extract_triples(text)

    assert {
        "subject": "人工智能",
        "relation": "是",
        "object": "计算机科学的分支",
    } in triples
    assert {
        "subject": "机器学习",
        "relation": "属于",
        "object": "人工智能",
    } in triples


def test_ignores_empty_text() -> None:
    assert knowledge_extractor.extract_triples("") == []
