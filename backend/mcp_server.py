"""可由 Claude Desktop、Codex 等 MCP Host 连接的 DeepStudy MCP Server。"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from backend.agent.tools import query_concept_graph
from backend.data.rag_store import get_document, list_documents
from backend.data.sqlite_db import get_db_connection
from backend.rag.service import rag_service

USER_ID = "anonymous"

mcp = FastMCP(
    "DeepStudy",
    instructions=(
        "提供课程资料检索、知识图谱查询、练习生成，以及课程/概念资源。"
        "课程事实必须保留 search_course 返回的引用信息。"
    ),
)


async def search_course_impl(
    query: str, session_id: str = "", top_k: int = 5
) -> dict[str, Any]:
    items = await rag_service.search(
        query,
        user_id=USER_ID,
        session_id=session_id or None,
        top_k=max(1, min(8, top_k)),
    )
    return {"query": query, "count": len(items), "items": items}


@mcp.tool(
    name="search_course",
    description="跨 DeepStudy 已索引课程资料进行混合检索，返回可引用片段。",
)
async def search_course(
    query: str, session_id: str = "", top_k: int = 5
) -> dict[str, Any]:
    return await search_course_impl(query, session_id, top_k)


@mcp.tool(
    name="query_concept_graph",
    description="查询概念及其前置、关联或相邻知识节点。",
)
async def concept_graph(concept: str, limit: int = 8) -> dict[str, Any]:
    try:
        return await query_concept_graph(concept, max(1, min(20, limit)))
    except Exception as exc:
        return {"query": concept, "count": 0, "items": [], "error": str(exc)[:240]}


@mcp.tool(
    name="create_quiz",
    description="围绕一个概念生成由易到难且暂不泄露答案的练习题。",
)
async def create_quiz(
    concept: str, difficulty: str = "adaptive", count: int = 3
) -> dict[str, Any]:
    count = max(1, min(6, count))
    templates = [
        ("理解", f"请用自己的话解释「{concept}」，并给出一个反例或边界情况。"),
        ("推理", f"给出一个必须使用「{concept}」才能解决的情境，并写出你的推理步骤。"),
        ("应用", f"把「{concept}」应用到一个新的实际问题，说明假设、方法和验证方式。"),
        ("辨析", f"比较「{concept}」与一个容易混淆的概念，指出至少两个关键区别。"),
        ("纠错", f"构造一个关于「{concept}」的常见错误说法，并解释错在哪里。"),
        ("迁移", f"将「{concept}」迁移到另一个学科或工程场景，并说明映射关系。"),
    ]
    questions = [
        {"index": index + 1, "level": level, "question": question}
        for index, (level, question) in enumerate(templates[:count])
    ]
    return {
        "concept": concept,
        "difficulty": difficulty,
        "questions": questions,
        "answer_policy": "用户作答后再逐题反馈，不在本次结果中直接给答案。",
    }


async def course_outline_impl(course_id: str) -> dict[str, Any]:
    document = await get_document(course_id, USER_ID)
    if not document:
        return {"error": "course document not found", "course_id": course_id}
    async with get_db_connection() as db:
        cursor = await db.execute(
            """
            SELECT section, MIN(chunk_index) AS first_chunk, COUNT(*) AS chunk_count,
                   MIN(page) AS first_page
            FROM rag_chunks WHERE document_id = ?
            GROUP BY section ORDER BY first_chunk ASC
            """,
            (course_id,),
        )
        sections = [dict(row) for row in await cursor.fetchall()]
    return {
        "course_id": course_id,
        "filename": document["filename"],
        "version": document["version"],
        "status": document["status"],
        "sections": sections,
    }


@mcp.resource(
    "course://{course_id}/outline",
    name="course-outline",
    description="已索引课程文档的章节大纲。",
    mime_type="application/json",
)
async def course_outline(course_id: str) -> str:
    return json.dumps(await course_outline_impl(course_id), ensure_ascii=False)


@mcp.resource(
    "concept://{concept_id}",
    name="concept-resource",
    description="知识图谱中的概念及其相邻关系。",
    mime_type="application/json",
)
async def concept_resource(concept_id: str) -> str:
    try:
        payload = await query_concept_graph(concept_id, 12)
    except Exception as exc:
        payload = {"query": concept_id, "count": 0, "items": [], "error": str(exc)[:240]}
    return json.dumps(payload, ensure_ascii=False)


@mcp.prompt(
    name="guided_explanation",
    description="生成以检索证据为约束的渐进式概念讲解提示词。",
)
def guided_explanation(concept: str, learner_level: str = "beginner") -> str:
    return (
        f"请为 {learner_level} 学习者渐进讲解「{concept}」。先调用 search_course 获取证据，"
        "再按直觉、定义、最小示例、边界条件、常见误区组织回答；课程事实保留引用编号。"
    )


@mcp.prompt(
    name="review_session",
    description="基于学习会话进行错因分析和巩固练习的提示词。",
)
def review_session(session_id: str, focus: str = "错因与迁移") -> str:
    return (
        f"复盘 DeepStudy 会话 {session_id}，重点关注{focus}。区分概念、推理、计算和审题错误，"
        "对不确定的判断明确标注，最后调用 create_quiz 给出不泄露答案的巩固题。"
    )


async def server_summary() -> dict[str, Any]:
    documents = await list_documents(session_id="", user_id=USER_ID)
    return {"name": "DeepStudy", "documents": len(documents)}


if __name__ == "__main__":
    mcp.run(transport="stdio")
