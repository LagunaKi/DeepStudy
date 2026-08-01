import asyncio

from backend.agent.activity_classifier import _parse_activity, classify_activity


def test_parse_activity_accepts_supported_values() -> None:
    assert _parse_activity("Explain") == "explain"
    assert _parse_activity("(derive)") == "derive"
    assert _parse_activity("practice。") == "practice"
    assert _parse_activity("[recall]") == "recall"


def test_parse_activity_rejects_unknown_values() -> None:
    assert _parse_activity("") is None
    assert _parse_activity("chat") is None
    assert _parse_activity("explanation") is None


def test_classify_activity_uses_local_rules_without_calling_llm() -> None:
    class FailingLLM:
        async def acomplete(self, _prompt: str):
            raise AssertionError("活动分类不应调用 LLM")

    async def classify() -> list[str | None]:
        llm = FailingLLM()
        return [
            await classify_activity(llm, "请推导这个公式"),
            await classify_activity(llm, "帮我写代码实现它"),
            await classify_activity(llm, "总结一下刚才的内容"),
            await classify_activity(llm, "什么是 RAG"),
        ]

    assert asyncio.run(classify()) == ["derive", "practice", "recall", "explain"]
