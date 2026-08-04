"""DeepStudy 教育场景意图分类器。

路由只决定教学策略和建议工具，不值得额外消耗一次模型请求。因此这里使用
可测试、可解释的确定性规则，并返回命中的安全摘要供 Agent Trace 展示。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Literal, Protocol


class LLM(Protocol):
    """保留旧 ``IntentRouter`` 构造接口所需的最小协议。"""

    async def acomplete(self, prompt: str): ...


class IntentType(str, Enum):
    """覆盖核心教学任务与系统控制任务的单一主意图。"""

    CONCEPT = "concept"
    DERIVATION = "derivation"
    CODE = "code"
    PROBLEM_SOLVING = "problem_solving"
    REVIEW = "review"
    QUIZ = "quiz"
    LEARNING_PROFILE = "learning_profile"
    COURSE_RETRIEVAL = "course_retrieval"
    CHITCHAT = "chitchat"
    FOLLOW_UP = "follow_up"
    SAFETY = "safety"


IntentCategory = Literal["educational", "system"]

INTENT_LABELS: dict[IntentType, str] = {
    IntentType.CONCEPT: "概念辨析与释义",
    IntentType.DERIVATION: "推导与定理证明",
    IntentType.CODE: "代码实现与调试",
    IntentType.PROBLEM_SOLVING: "解题与作业辅导",
    IntentType.REVIEW: "总结与提炼",
    IntentType.QUIZ: "出题与自测",
    IntentType.LEARNING_PROFILE: "学习画像与路径",
    IntentType.COURSE_RETRIEVAL: "课程资料查考",
    IntentType.CHITCHAT: "闲聊与身份询问",
    IntentType.FOLLOW_UP: "上下文追问",
    IntentType.SAFETY: "拒答与安全边界",
}

SYSTEM_INTENTS = frozenset(
    {IntentType.CHITCHAT, IntentType.FOLLOW_UP, IntentType.SAFETY}
)


@dataclass(frozen=True)
class IntentDecision:
    intent: IntentType
    category: IntentCategory
    label: str
    confidence: float
    signals: tuple[str, ...]


_SAFETY_PATTERNS = (
    r"(?:教我|帮我|如何|怎么)(?:(?:入侵|攻击).{0,6}(?:网站|服务器|账号|系统|网络)"
    r"|绕过验证|窃取密码|制作炸弹|自残)",
    r"(?:股票|彩票|赌博).{0,6}(?:推荐|稳赚|预测)",
    r"(?:帮我订餐|写情书|旅游攻略|今天天气)",
)

_FOLLOW_UP_EXACT = frozenset(
    {
        "下一步呢",
        "然后呢",
        "为什么",
        "为什么呢",
        "继续",
        "继续讲",
        "再说说",
        "那这个呢",
        "这个呢",
        "能展开吗",
        "详细一点",
        "再解释一下",
        "什么意思",
    }
)

_CHITCHAT_PATTERNS = (
    r"(?:你好|嗨|hello|hi|在吗)[！!。.？?]*",
    r"(?:(?:你好|嗨|hello|hi)[,，]?)?(?:你是谁|你叫什么|介绍一下你自己)[？?。]*",
    r"(?:谢谢|感谢|辛苦了|再见)[！!。.]*",
)

_RULES: tuple[tuple[IntentType, tuple[str, ...], tuple[str, ...]], ...] = (
    (
        IntentType.LEARNING_PROFILE,
        (
            "学习画像",
            "学习进度",
            "我的掌握",
            "掌握得怎么样",
            "最薄弱",
            "薄弱点",
            "下一步学习",
            "学习计划",
            "学习路径",
        ),
        (r"我目前.{0,12}(?:学到|掌握|薄弱)", r"推荐.{0,8}(?:学习|复习).{0,8}(?:路径|计划|内容)"),
    ),
    (
        IntentType.QUIZ,
        ("出题", "练习题", "测验", "考考我", "闪卡", "flashcard", "quiz", "自测"),
        (r"(?:给我|帮我|生成).{0,8}\d*.{0,4}(?:题|选择题|判断题)",),
    ),
    (
        IntentType.CODE,
        (
            "代码",
            "编程",
            "python",
            "javascript",
            "typescript",
            "java",
            "c++",
            "报错",
            "bug",
            "debug",
            "indexerror",
            "typeerror",
            "函数实现",
            "算法实现",
        ),
        (r"(?:实现|调试|修复|运行).{0,10}(?:函数|程序|脚本|代码)",),
    ),
    (
        IntentType.DERIVATION,
        ("推导", "证明", "定理证明", "公式推演", "为什么成立", "derive", "prove", "proof"),
        (r"(?:求|写出).{0,12}(?:导数|梯度|偏导|闭式解)", r"从.{0,10}推到"),
    ),
    (
        IntentType.PROBLEM_SOLVING,
        ("这道题", "这题", "怎么做", "解题", "作业辅导", "帮我分析", "选a还是b", "答案选"),
        (
            r"(?:选择题|填空题|计算题|证明题).{0,12}(?:怎么|选|分析|求)",
            r"(?:题目|已知).{0,30}(?:求|问)",
        ),
    ),
    (
        IntentType.REVIEW,
        ("总结", "概括", "提炼", "回顾", "复习", "知识点梳理", "总结一下", "review"),
        (r"(?:帮我|请).{0,6}(?:梳理|整理).{0,12}(?:知识点|重点|内容)",),
    ),
    (
        IntentType.COURSE_RETRIEVAL,
        ("课程资料", "上传的", "文档里", "讲义里", "课件里", "ppt里", "教材里", "附件里"),
        (
            r"(?:文档|资料|讲义|课件|ppt|教材).{0,12}(?:要求|内容|提到|怎么说|是什么)",
            r"老师.{0,12}(?:布置|要求|讲过)",
        ),
    ),
    (
        IntentType.CONCEPT,
        ("什么是", "解释", "讲解", "区别", "原理", "含义", "概念", "为什么会"),
        (r".+和.+有什么区别",),
    ),
)


def _clean_query(query: str) -> str:
    return re.sub(r"\s+", "", (query or "").casefold()).strip("。！？!?，,；;")


def _is_follow_up(normalized: str, *, has_context: bool) -> bool:
    if normalized in _FOLLOW_UP_EXACT:
        return True
    if not has_context or len(normalized) > 24:
        return False
    return bool(
        re.search(
            r"(?:这个|那个|它|上面|刚才|前面|这一步|第二步|上一条).{0,10}"
            r"(?:呢|吗|为什么|怎么|什么意思|展开)",
            normalized,
        )
    )


def classify_intent(
    query: str,
    *,
    has_context: bool = False,
    has_attachments: bool = False,
) -> IntentDecision:
    """返回可解释的主意图；规则命中信息只用于 Trace，不包含思维链。"""
    normalized = _clean_query(query)

    safety_signal = next(
        (pattern for pattern in _SAFETY_PATTERNS if re.search(pattern, normalized)),
        None,
    )
    if safety_signal:
        return IntentDecision(
            intent=IntentType.SAFETY,
            category="system",
            label=INTENT_LABELS[IntentType.SAFETY],
            confidence=0.98,
            signals=("safety_boundary",),
        )

    if _is_follow_up(normalized, has_context=has_context):
        return IntentDecision(
            intent=IntentType.FOLLOW_UP,
            category="system",
            label=INTENT_LABELS[IntentType.FOLLOW_UP],
            confidence=0.9 if has_context else 0.72,
            signals=("context_reference",),
        )

    if any(re.fullmatch(pattern, normalized) for pattern in _CHITCHAT_PATTERNS):
        return IntentDecision(
            intent=IntentType.CHITCHAT,
            category="system",
            label=INTENT_LABELS[IntentType.CHITCHAT],
            confidence=0.96,
            signals=("smalltalk",),
        )

    scores: dict[IntentType, float] = {}
    signals: dict[IntentType, list[str]] = {}
    for intent, phrases, patterns in _RULES:
        matched_phrases = [phrase for phrase in phrases if phrase in normalized]
        matched_patterns = [pattern for pattern in patterns if re.search(pattern, normalized)]
        if not matched_phrases and not matched_patterns:
            continue
        scores[intent] = len(matched_phrases) * 3 + len(matched_patterns) * 5
        signals[intent] = [*matched_phrases[:3], *("pattern" for _ in matched_patterns[:1])]

    if has_attachments:
        scores[IntentType.COURSE_RETRIEVAL] = scores.get(IntentType.COURSE_RETRIEVAL, 0) + 1.5
        signals.setdefault(IntentType.COURSE_RETRIEVAL, []).append("attachment")

    if not scores:
        selected = IntentType.CONCEPT
        selected_signals = ("default",)
        confidence = 0.55
    else:
        selected = max(scores, key=lambda intent: scores[intent])
        selected_signals = tuple(signals[selected])
        confidence = min(0.97, 0.62 + scores[selected] * 0.045)

    return IntentDecision(
        intent=selected,
        category="system" if selected in SYSTEM_INTENTS else "educational",
        label=INTENT_LABELS[selected],
        confidence=round(confidence, 2),
        signals=selected_signals,
    )


class IntentRouter:
    """兼容旧调用方的异步包装；不再调用 LLM。"""

    def __init__(self, llm: LLM | None = None) -> None:
        self.llm = llm

    async def route(self, query: str) -> IntentType:
        return classify_intent(query).intent
