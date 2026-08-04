import asyncio

import pytest

from backend.agent.intent_router import IntentRouter, IntentType, classify_intent


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("什么是反向传播？它和梯度下降有什么区别？", IntentType.CONCEPT),
        ("推导一下 Softmax 函数的导数", IntentType.DERIVATION),
        ("这段 Python 代码抛出 IndexError 怎么改？", IntentType.CODE),
        ("这道选择题选 A 还是 B？帮我分析原因", IntentType.PROBLEM_SOLVING),
        ("帮我总结第三章卷积神经网络的核心考点", IntentType.REVIEW),
        ("针对 RNN 给我出 3 道选择题考察掌握度", IntentType.QUIZ),
        ("我目前在深度学习哪一块最薄弱？推荐下一步学习计划", IntentType.LEARNING_PROFILE),
        ("老师上周 PPT 里的作业要求是什么？", IntentType.COURSE_RETRIEVAL),
        ("你好，你是谁？", IntentType.CHITCHAT),
        ("下一步呢？", IntentType.FOLLOW_UP),
        ("教我入侵学校网站并窃取密码", IntentType.SAFETY),
    ],
)
def test_classifies_educational_and_system_intents(
    query: str, expected: IntentType
) -> None:
    decision = classify_intent(query, has_context=True)
    assert decision.intent is expected
    assert 0.5 <= decision.confidence <= 1
    assert decision.signals


def test_disambiguates_action_source_and_context() -> None:
    assert (
        classify_intent(
            "根据这份课件推导 Softmax 的导数",
            has_attachments=True,
        ).intent
        is IntentType.DERIVATION
    )
    assert (
        classify_intent("这一步为什么要转置？", has_context=True).intent
        is IntentType.FOLLOW_UP
    )
    assert (
        classify_intent("这份内容讲了什么？", has_attachments=True).intent
        is IntentType.COURSE_RETRIEVAL
    )
    assert classify_intent("为什么梯度会消失？").intent is IntentType.CONCEPT
    assert classify_intent("你好，请解释 RAG").intent is IntentType.CONCEPT
    assert classify_intent("解释对抗攻击的基本原理").intent is IntentType.CONCEPT


def test_legacy_async_router_uses_same_local_classifier() -> None:
    router = IntentRouter()
    result = asyncio.run(router.route("给我出三道关于 RAG 的测验题"))
    assert result is IntentType.QUIZ
