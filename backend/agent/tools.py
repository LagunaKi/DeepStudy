"""DeepStudy 原生 Agent 工具及统一注册表。"""

import ast
import inspect
import logging
import operator
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from google.genai import types
from pydantic import BaseModel, Field, ValidationError

from backend.data.neo4j_client import neo4j_client
from backend.data.profile_store import get_all_profiles

logger = logging.getLogger(__name__)


class CalculateExpressionInput(BaseModel):
    expression: str = Field(
        ...,
        min_length=1,
        max_length=300,
        description="只包含数字、括号和常见算术运算符的表达式",
    )


class LearningProfileInput(BaseModel):
    limit: int = Field(8, ge=1, le=20, description="最多返回多少个学习概念")


class ConceptGraphInput(BaseModel):
    concept: str = Field(..., min_length=1, max_length=80, description="要查找的概念名")
    limit: int = Field(8, ge=1, le=20, description="最多返回多少个相关节点")


class CourseSearchInput(BaseModel):
    query: str = Field(..., min_length=1, max_length=300, description="课程资料检索词")
    top_k: int = Field(3, ge=1, le=8, description="返回片段数量")


_BINARY_OPERATORS: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPERATORS: dict[type[ast.unaryop], Callable[[float], float]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _evaluate_ast(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _evaluate_ast(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
        left = _evaluate_ast(node.left)
        right = _evaluate_ast(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 12:
            raise ValueError("指数绝对值不能超过 12")
        result = _BINARY_OPERATORS[type(node.op)](left, right)
        if abs(result) > 1e100:
            raise ValueError("计算结果过大")
        return result
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
        return _UNARY_OPERATORS[type(node.op)](_evaluate_ast(node.operand))
    raise ValueError("表达式包含不允许的语法")


async def calculate_expression(expression: str) -> dict[str, Any]:
    """在无 eval 的白名单 AST 中计算算术表达式。"""
    tree = ast.parse(expression, mode="eval")
    value = _evaluate_ast(tree)
    normalized: int | float = int(value) if value.is_integer() else round(value, 12)
    return {"expression": expression, "value": normalized}


async def get_learning_profile(limit: int = 8, *, user_id: str) -> dict[str, Any]:
    profiles = await get_all_profiles(user_id=user_id)
    concepts = [
        {
            "concept": item.concept_key,
            "understanding": round(item.u, 3),
            "reasoning": round(item.r, 3),
            "application": round(item.a, 3),
            "score": round(item.score, 3),
            "practice_count": item.times,
        }
        for item in profiles[:limit]
    ]
    return {"concepts": concepts, "count": len(concepts)}


async def query_concept_graph(concept: str, limit: int = 8) -> dict[str, Any]:
    records = await neo4j_client.query(
        """
        MATCH (n)
        WHERE toLower(coalesce(n.title, n.name, n.content, ''))
              CONTAINS toLower($concept)
        OPTIONAL MATCH (n)-[r]-(related)
        RETURN coalesce(n.title, n.name, n.content) AS concept,
               type(r) AS relation,
               coalesce(related.title, related.name, related.content) AS related
        LIMIT $limit
        """,
        {"concept": concept, "limit": limit},
    )
    items = [
        {
            "concept": record.get("concept"),
            "relation": record.get("relation"),
            "related": record.get("related"),
        }
        for record in records
    ]
    return {"query": concept, "items": items, "count": len(items)}


async def search_course_materials(
    query: str, top_k: int = 3, *, user_id: str, session_id: str
) -> dict[str, Any]:
    from backend.rag.service import rag_service

    items = await rag_service.search(
        query,
        user_id=user_id,
        session_id=session_id,
        top_k=top_k,
    )
    return {
        "query": query,
        "items": items,
        "available": bool(items),
        "count": len(items),
        "message": "" if items else "当前会话没有可用的课程资料证据。",
    }


ToolHandler = Callable[..., dict[str, Any] | Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: ToolHandler
    inject_user_id: bool = False
    inject_session_id: bool = False

    def gemini_declaration(self) -> types.FunctionDeclaration:
        schema = self.input_model.model_json_schema()
        schema.pop("title", None)
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters_json_schema=schema,
        )


class ToolRegistry:
    def __init__(self, definitions: list[ToolDefinition] | None = None) -> None:
        definitions = definitions or DEFAULT_TOOLS
        self._tools = {definition.name: definition for definition in definitions}

    @property
    def names(self) -> list[str]:
        return list(self._tools)

    def declarations(self) -> list[types.FunctionDeclaration]:
        return [definition.gemini_declaration() for definition in self._tools.values()]

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        user_id: str,
        session_id: str = "",
        call_id: str = "",
    ) -> dict[str, Any]:
        started = time.perf_counter()
        definition = self._tools.get(name)
        if definition is None:
            return self._error_record(name, arguments, call_id, started, "未知工具")

        try:
            validated = definition.input_model.model_validate(arguments)
            kwargs = validated.model_dump()
            if definition.inject_user_id:
                kwargs["user_id"] = user_id
            if definition.inject_session_id:
                kwargs["session_id"] = session_id
            result = definition.handler(**kwargs)
            if inspect.isawaitable(result):
                result = await result
            summary = self._summarize_result(result)
            return {
                "name": name,
                "call_id": call_id,
                "arguments": validated.model_dump(),
                "status": "success",
                "result": result,
                "summary": summary,
                "duration_ms": round((time.perf_counter() - started) * 1000),
            }
        except (ValidationError, ValueError, SyntaxError, ZeroDivisionError) as exc:
            return self._error_record(name, arguments, call_id, started, str(exc))
        except Exception as exc:  # 外部存储失败必须降级，不能打断整轮回答
            logger.warning("Agent 工具调用失败: tool=%s error=%s", name, exc, exc_info=True)
            return self._error_record(name, arguments, call_id, started, "工具暂时不可用")

    @staticmethod
    def _summarize_result(result: dict[str, Any]) -> str:
        if "value" in result:
            return f"计算结果：{result['value']}"
        if "count" in result:
            return f"返回 {result['count']} 条结果"
        if result.get("available") is False:
            return str(result.get("message") or "数据源不可用")
        return "工具执行成功"

    @staticmethod
    def _error_record(
        name: str,
        arguments: dict[str, Any],
        call_id: str,
        started: float,
        message: str,
    ) -> dict[str, Any]:
        return {
            "name": name,
            "call_id": call_id,
            "arguments": arguments,
            "status": "error",
            "result": {"error": message},
            "summary": message,
            "duration_ms": round((time.perf_counter() - started) * 1000),
        }


DEFAULT_TOOLS = [
    ToolDefinition(
        name="calculate_expression",
        description="精确计算算术表达式。遇到具体数值计算时应使用，不能用来执行代码。",
        input_model=CalculateExpressionInput,
        handler=calculate_expression,
    ),
    ToolDefinition(
        name="get_learning_profile",
        description="读取当前用户的概念掌握度与练习次数，用于个性化讲解。",
        input_model=LearningProfileInput,
        handler=get_learning_profile,
        inject_user_id=True,
    ),
    ToolDefinition(
        name="query_concept_graph",
        description="从 Neo4j 查询概念及其相邻关系，适合前置知识、关联概念和学习路径问题。",
        input_model=ConceptGraphInput,
        handler=query_concept_graph,
    ),
    ToolDefinition(
        name="search_course_materials",
        description="检索用户已经索引的课程资料。仅在问题要求依据课程资料时使用。",
        input_model=CourseSearchInput,
        handler=search_course_materials,
        inject_user_id=True,
        inject_session_id=True,
    ),
]
