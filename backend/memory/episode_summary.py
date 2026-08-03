"""无需额外模型调用的学习情景摘要与展示标签。"""

from __future__ import annotations

import re
from typing import Any, TypedDict


class EpisodeSummary(TypedDict):
    content: str
    title: str
    primary_concept: str
    related_concepts: list[str]
    concepts: list[str]
    activity: str
    activity_label: str
    skill: str
    skill_label: str
    tools: list[str]
    tool_labels: list[str]


ACTIVITY_LABELS = {
    "explain": "概念讲解",
    "derive": "公式推导",
    "practice": "练习应用",
    "recall": "回顾复习",
}

SKILL_LABELS = {
    "explain-concept": "概念讲解",
    "derive-formula": "公式推导",
    "generate-practice": "生成练习",
    "review-mistakes": "错题复盘",
    "default": "通用学习",
    "": "通用学习",
}

TOOL_LABELS = {
    "calculate_expression": "计算器",
    "get_learning_profile": "学习画像",
    "query_concept_graph": "概念图谱",
    "search_course_materials": "课程资料检索",
}

_QUERY_PREFIXES = (
    r"^(?:请|麻烦)?(?:给我)?(?:系统地?)?(?:学习|讲解|解释|介绍|了解|掌握)",
    r"^我(?:想|希望|需要)(?:要)?(?:系统地?)?(?:学习|了解|掌握)?",
    r"^你还记得我之前(?:问|学)(?:过)?(?:的|你的)?(?:有关|关于)?",
    r"^(?:有关|关于)",
)

_SENTENCE_MARKERS = (
    "什么是", "是什么", "为什么", "如何", "怎么", "能否", "是否",
    "请问", "告诉我", "你还记得", "我之前问", "我想", "我希望",
)

_GENERIC_CONCEPTS = {
    "核心概念", "详细解释", "概念讲解", "公式推导", "总结", "示例",
    "常见误区", "应用场景", "学习目标", "前置知识", "资料依据",
}


def _clean(value: str) -> str:
    value = re.sub(r"^[#\s\d.、:：-]+", "", str(value))
    value = re.sub(r"[（(][A-Za-z][^（）()]{0,40}[）)]", "", value)
    value = value.strip(" \t\n：:，,。.!！?？【】[]*`_-—\"'“”")
    return re.sub(r"\s+", " ", value)


def _strip_query_prefix(value: str) -> str:
    cleaned = _clean(value)
    for pattern in _QUERY_PREFIXES:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    return _clean(cleaned)


def _is_concept(value: str) -> bool:
    if not value or len(value) > 24 or value in _GENERIC_CONCEPTS:
        return False
    if any(marker in value for marker in _SENTENCE_MARKERS):
        return False
    if re.search(r"[。！？?；;]", value):
        return False
    return bool(re.search(r"[A-Za-z0-9\u3400-\u9fff]", value))


def _query_candidates(query: str) -> list[str]:
    candidates: list[str] = []
    # 英文技术缩写通常是最稳定的主概念，例如 RAG、MCP、LLM。
    candidates.extend(re.findall(r"(?<![A-Za-z])[A-Z][A-Z0-9-]{1,15}(?![A-Za-z])", query))
    for clause in re.split(r"[，,、；;。！？?\n]+", query):
        clause = _strip_query_prefix(clause)
        if not clause:
            continue
        relation = re.fullmatch(
            r"(.{2,10}?)(?:如何|怎么)(?:处理|解决|使用|实现)(.{2,10})",
            clause,
        )
        if relation:
            candidates.extend([_clean(relation.group(1)), _clean(relation.group(2))])
            continue
        if clause.startswith("减少") and 3 <= len(clause) <= 10:
            candidates.append(f"{clause[2:]}问题")
            continue
        candidates.append(clause)
    return candidates


def _canonicalize(value: str) -> str:
    cleaned = _clean(value)
    folded = cleaned.casefold()
    aliases = {
        "rag": "RAG",
        "mcp": "MCP",
        "llm": "LLM",
        "agent": "Agent",
        "ai": "AI",
        "大语言模型": "大模型",
        "模型幻觉问题": "模型幻觉",
        "幻觉问题": "模型幻觉",
    }
    return aliases.get(folded, cleaned)


def select_episode_concepts(query: str, concepts: list[str], limit: int = 5) -> list[str]:
    """从问题和回答概念中选出一个主概念及少量相关概念。"""
    values = [*_query_candidates(query), *concepts]
    selected: list[str] = []
    seen: set[str] = set()
    for raw in values:
        candidate = _canonicalize(_strip_query_prefix(raw))
        folded = candidate.casefold()
        if not _is_concept(candidate) or folded in seen:
            continue
        # RAG 与中文全称同时出现时保留更适合作为界面标题的 RAG。
        if candidate == "检索增强生成" and "rag" in seen:
            continue
        if candidate == "RAG" and "检索增强生成" in seen:
            selected = [item for item in selected if item != "检索增强生成"]
            seen.discard("检索增强生成")
        # "RAG 的核心思想"这类标题不应与更短的 RAG 重复出现。
        if any(
            len(existing) >= 2
            and (folded in existing.casefold() or existing.casefold() in folded)
            for existing in selected
        ):
            continue
        seen.add(folded)
        selected.append(candidate)
        if len(selected) >= max(1, limit):
            break
    return selected or ["本轮学习主题"]


def build_episode_summary(
    *,
    query: str,
    concepts: list[str],
    activity: str,
    skill: str,
    tools: list[str] | None = None,
) -> EpisodeSummary:
    selected = select_episode_concepts(query, concepts)
    primary, related = selected[0], selected[1:]
    activity_label = ACTIVITY_LABELS.get(activity, "学习探索")
    skill_label = SKILL_LABELS.get(skill, skill or "通用学习")
    method_label = skill_label if skill_label != "通用学习" else activity_label
    content_parts = [f"本轮学习：{primary}"]
    if related:
        content_parts.append(f"关联概念：{'、'.join(related)}")
    content_parts.append(f"学习方式：{method_label}")
    tool_names = list(dict.fromkeys(name for name in (tools or []) if name))
    return {
        "content": "；".join(content_parts) + "。",
        "title": primary,
        "primary_concept": primary,
        "related_concepts": related,
        "concepts": selected,
        "activity": activity,
        "activity_label": activity_label,
        "skill": skill,
        "skill_label": skill_label,
        "tools": tool_names,
        "tool_labels": [TOOL_LABELS.get(name, name) for name in tool_names],
    }


def improve_legacy_episode(item: dict[str, Any]) -> dict[str, Any]:
    """让阶段 3 已生成的旧情景在读取时也使用新版摘要。"""
    if item.get("scope") != "episodic" or item.get("kind") != "learning_turn":
        return item
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    concepts = metadata.get("concepts")
    if not isinstance(concepts, list) or not concepts:
        return item
    summary = build_episode_summary(
        query=str(metadata.get("query") or concepts[0]),
        concepts=[str(value) for value in concepts],
        activity=str(metadata.get("activity") or "explain"),
        skill=str(metadata.get("skill") or ""),
        tools=[str(value) for value in metadata.get("tools", []) if value],
    )
    item["content"] = summary["content"]
    item["metadata"] = {**metadata, **summary}
    return item
