"""学习活动类型分类器。

活动类型只用于更新学习画像，不值得占用一次免费模型请求，因此使用确定性规则判别。
"""
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

VALID_ACTIVITIES = frozenset({"explain", "derive", "practice", "recall"})


def _parse_activity(raw: str) -> str | None:
    """
    从 LLM 输出中解析出单一活动类型。
    只认 explain / derive / practice / recall（忽略大小写），否则返回 None。
    """
    if not raw or not isinstance(raw, str):
        return None
    text = raw.strip().lower()
    text = re.sub(r"^[\[\(]?\s*", "", text)
    text = re.sub(r"\s*[\]\)\.]?\s*$", "", text)
    first_word = (re.split(r"[\s,，。、]+", text)[0] or "").strip()
    return first_word if first_word in VALID_ACTIVITIES else None


async def classify_activity(
    llm: Any,
    query: str,
    answer_snippet: str | None = None,
) -> str | None:
    """
    根据用户问题判别本次学习活动类型，不再调用 LLM。

    Args:
        llm: 为兼容现有调用保留，不会被调用
        query: 用户问题
        answer_snippet: 可选，回答内容摘要（如 full_answer[:300]）

    Returns:
        "explain" | "derive" | "practice" | "recall"，无法判定或异常时返回 None
    """
    if not query or not query.strip():
        return None

    del llm, answer_snippet
    normalized = query.strip().lower()

    keyword_groups = (
        (
            "recall",
            ("复述", "回顾", "回忆", "再讲", "重新讲", "总结", "概括", "recall", "review"),
        ),
        (
            "derive",
            ("推导", "证明", "论证", "推理过程", "因果链", "derive", "prove", "proof"),
        ),
        (
            "practice",
            (
                "做题",
                "练习",
                "计算",
                "写代码",
                "实现",
                "调试",
                "报错",
                "应用",
                "例题",
                "practice",
                "code",
                "debug",
                "implement",
            ),
        ),
    )
    for activity, keywords in keyword_groups:
        if any(keyword in normalized for keyword in keywords):
            logger.info("活动类型规则判别: %s", activity)
            return activity

    logger.info("活动类型规则判别: explain")
    return "explain"
