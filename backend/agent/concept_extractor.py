"""无需额外 LLM 请求的学习地图概念提取。"""

import re
from typing import TypedDict


class ConceptStructure(TypedDict):
    root: str
    children: list[str]

_QUERY_FILLERS = (
    "给我讲一下",
    "给我讲讲",
    "请详细解释",
    "详细解释",
    "仔细讲解",
    "具体讲一下",
    "解释一下",
    "什么是",
    "是什么",
    "请",
    "这个",
)

_GENERIC_LABELS = {
    "总结",
    "一句话总结",
    "背景知识",
    "应用场景",
    "现实生活中的应用场景",
    "关键术语",
    "通俗易懂的解释",
    "举个例子",
}


def _clean_label(value: str) -> str:
    value = re.sub(r"^[#\s\d.、:：-]+", "", value)
    value = re.sub(r"[（(][^（）()]{0,40}[）)]", "", value)
    value = value.strip(" \t\n：:，,。.!！?？【】[]*`_-—")
    return re.sub(r"\s+", " ", value)


def _query_root(query: str) -> str:
    root = query.strip()
    for filler in _QUERY_FILLERS:
        root = root.replace(filler, "")
    root = _clean_label(root)
    return root[:24] or "核心概念"


def extract_concept_structure(query: str, answer: str) -> ConceptStructure:
    """从问题与 Markdown 回答中提取一个根概念和最多五个子概念。"""
    root = _query_root(query)
    headings = re.findall(r"^#{1,6}\s+(.+)$", answer, flags=re.MULTILINE)
    emphasized = re.findall(r"\*\*([^*\n]{2,60})\*\*", answer)

    children: list[str] = []
    seen = {root.casefold()}
    for raw_label in [*emphasized, *headings]:
        label = _clean_label(raw_label)
        folded = label.casefold()
        if (
            not label
            or len(label) > 24
            or folded in seen
            or any(generic in label for generic in _GENERIC_LABELS)
            or label.startswith("什么是")
        ):
            continue
        seen.add(folded)
        children.append(label)
        if len(children) == 5:
            break

    return {"root": root, "children": children}
