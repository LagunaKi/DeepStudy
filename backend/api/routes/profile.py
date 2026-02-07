"""
学习画像相关路由
"""
from typing import List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from backend.api.schemas.response import MindMapGraph
from backend.data.profile_store import (
    ANONYMOUS_USER_ID,
    add_to_learning_plan,
    delete_concept_profile,
    get_all_profiles,
    get_learning_plan,
    get_weak_profiles,
    remove_from_learning_plan,
)


class ConceptProfileSummary(BaseModel):
    """概念画像摘要"""

    concept: str = Field(..., description="规范化后的概念名")
    u: float = Field(..., description="理解维度 (0-1)")
    r: float = Field(..., description="推理维度 (0-1)")
    a: float = Field(..., description="应用维度 (0-1)")
    times: int = Field(..., description="练习次数")
    last_practice: Optional[str] = Field(
        None,
        description="最近一次练习时间（ISO 格式，可为空）",
    )
    score: float = Field(..., description="综合得分（简单取三维平均）")


router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/summary", response_model=List[ConceptProfileSummary])
async def get_profile_summary() -> List[ConceptProfileSummary]:
    """
    获取当前用户的概念画像摘要列表。
    单用户场景下，用户 ID 固定为 anonymous。
    """
    profiles = await get_all_profiles(user_id=ANONYMOUS_USER_ID)
    result: List[ConceptProfileSummary] = []
    for p in profiles:
        last_ts = p.last_practice.isoformat() if p.last_practice else None
        result.append(
            ConceptProfileSummary(
                concept=p.concept_key,
                u=p.u,
                r=p.r,
                a=p.a,
                times=p.times,
                last_practice=last_ts,
                score=p.score,
            ),
        )
    return result


class DeleteConceptBody(BaseModel):
    """删除概念请求体"""

    concept: str = Field(..., description="要删除的概念名（concept_key）")


@router.delete("/concepts")
async def delete_concept(body: DeleteConceptBody) -> None:
    """
    从学习画像中删除指定概念。仅删除 concept_profiles 中的行，保留 conversation_concepts 追溯。
    """
    await delete_concept_profile(concept_key=body.concept, user_id=ANONYMOUS_USER_ID)


@router.get("/plan", response_model=List[str])
async def get_plan() -> List[str]:
    """
    获取当前用户的学习计划（概念名列表）。
    """
    return await get_learning_plan(user_id=ANONYMOUS_USER_ID)


class PlanConceptBody(BaseModel):
    """学习计划单项请求体"""

    concept: str = Field(..., description="概念名（concept_key）")


@router.post("/plan")
async def add_concept_to_plan(body: PlanConceptBody) -> None:
    """将概念加入学习计划。"""
    await add_to_learning_plan(concept_key=body.concept, user_id=ANONYMOUS_USER_ID)


@router.delete("/plan")
async def remove_concept_from_plan(body: PlanConceptBody) -> None:
    """从学习计划中移除概念。"""
    await remove_from_learning_plan(concept_key=body.concept, user_id=ANONYMOUS_USER_ID)


@router.get("/weak", response_model=List[ConceptProfileSummary])
async def get_weak_concepts(
    limit: int = Query(10, ge=1, le=100, description="返回薄弱概念的数量"),
) -> List[ConceptProfileSummary]:
    """
    获取当前用户的薄弱概念列表。
    按理解维度 U 从低到高排序，返回前 N 个。
    """
    profiles = await get_weak_profiles(user_id=ANONYMOUS_USER_ID, limit=limit)
    result: List[ConceptProfileSummary] = []
    for p in profiles:
        last_ts = p.last_practice.isoformat() if p.last_practice else None
        result.append(
            ConceptProfileSummary(
                concept=p.concept_key,
                u=p.u,
                r=p.r,
                a=p.a,
                times=p.times,
                last_practice=last_ts,
                score=p.score,
            ),
        )
    return result


@router.get("/graph", response_model=MindMapGraph)
async def get_profile_graph() -> MindMapGraph:
    """
    获取画像图结构视图。
    为简化实现，目前仅返回概念节点列表，不包含概念间连边：
    - 节点 ID 使用概念名
    - data 中包含 (u, r, a, score, times)
    前端可使用这些节点构造自定义可视化。
    """
    profiles = await get_all_profiles(user_id=ANONYMOUS_USER_ID)
    if not profiles:
        return MindMapGraph(nodes=[], edges=[])

    nodes = []
    for p in profiles:
        nodes.append(
            {
                "id": p.concept_key,
                "type": "default",
                "data": {
                    "label": p.concept_key,
                    "type": "concept",
                    "u": p.u,
                    "r": p.r,
                    "a": p.a,
                    "score": p.score,
                    "times": p.times,
                },
            },
        )

    return MindMapGraph(nodes=nodes, edges=[])
