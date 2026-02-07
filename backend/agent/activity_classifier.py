"""
活动类型分类器
根据用户问题与回答摘要，用 LLM 判别学习活动类型：explain / derive / practice / recall
"""
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

VALID_ACTIVITIES = frozenset({"explain", "derive", "practice", "recall"})


def _parse_activity(raw: str) -> Optional[str]:
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
    answer_snippet: Optional[str] = None,
) -> Optional[str]:
    """
    根据用户问题与回答摘要，判别本次学习活动类型。

    Args:
        llm: 具备 acomplete(prompt) 的 LLM 实例（如 Orchestrator 的 self.llm）
        query: 用户问题
        answer_snippet: 可选，回答内容摘要（如 full_answer[:300]）

    Returns:
        "explain" | "derive" | "practice" | "recall"，无法判定或异常时返回 None
    """
    if not query or not query.strip():
        return None

    prompt = """你是一个学习活动分类器。根据「用户问题」和（若有）「回答摘要」，判断这次学习活动属于以下哪一种，只输出一个英文单词，不要解释。

活动类型说明：
- explain：理解、定义、是什么、为什么（偏概念理解）
- derive：推导、证明、论证、因果链、步骤推理
- practice：做题、写代码、应用、举例分析、用概念解决问题
- recall：复述、回顾、再讲一遍、总结

只输出一个词：explain、derive、practice 或 recall。

用户问题：
"""
    prompt += f'"{query.strip()[:500]}"\n\n'
    if answer_snippet and answer_snippet.strip():
        prompt += "回答摘要：\n"
        prompt += f'"{answer_snippet.strip()[:400]}"\n\n'
    prompt += "活动类型："

    try:
        response = await llm.acomplete(prompt)
        text = getattr(response, "text", None) or str(response)
        activity = _parse_activity(text)
        if activity:
            logger.info("活动类型判别: %s", activity)
        else:
            logger.warning("活动类型解析失败，原始返回: %s", text[:200])
        return activity
    except Exception as e:
        logger.warning("活动类型分类 LLM 调用失败: %s", e, exc_info=True)
        return None
