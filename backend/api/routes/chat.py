"""
聊天相关路由
"""
import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from backend.agent.llm_client import LLMRateLimitError
from backend.agent.orchestrator import AgentOrchestrator
from backend.api.schemas.request import ChatRequest
from backend.api.schemas.response import DialogueNodeBase
from backend.data.conversation_store import add_message
from backend.data.neo4j_client import neo4j_client
from backend.data.rag_store import (
    get_attachments,
    link_attachments_to_message,
)

# 配置日志
logger = logging.getLogger(__name__)

# 匿名用户 ID（移除登录后所有用户共用）
ANONYMOUS_USER_ID = "anonymous"

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("")
async def chat(request: ChatRequest):
    """
    发送聊天消息（支持普通提问和划词追问），使用 HTTP 流式返回结果。
    """
    user_id = ANONYMOUS_USER_ID
    
    logger.info(
        "收到聊天请求: user_id=%s, query=%s...",
        user_id,
        request.query[:50] if len(request.query) > 50 else request.query,
    )
    logger.info(
        "请求详情: parent_id=%s, ref_fragment_id=%s, session_id=%s",
        request.parent_id,
        request.ref_fragment_id,
        request.session_id,
    )

    try:
        logger.info("初始化 Orchestrator...")
        orchestrator = AgentOrchestrator()
        logger.info("Orchestrator 初始化成功")

        attachments = await get_attachments(request.attachment_ids, request.session_id)
        if len(attachments) != len(set(request.attachment_ids)):
            raise HTTPException(status_code=400, detail="部分附件不存在或不属于当前会话")

        # 统一使用流式输出
        if request.ref_fragment_id:
            logger.info("处理划词追问（流式）...")
            token_stream = orchestrator.process_recursive_query_stream(
                user_id=user_id,
                parent_id=request.parent_id or "",
                fragment_id=request.ref_fragment_id,
                query=request.query,
                selected_text=request.selected_text,
                session_id=request.session_id,
                attachments=attachments,
            )
        else:
            logger.info("处理普通提问（流式）...")
            token_stream = orchestrator.process_query_stream(
                user_id=user_id,
                query=request.query,
                parent_id=request.parent_id,
                session_id=request.session_id,
                attachments=attachments,
            )

        user_message = await add_message(
            session_id=request.session_id,
            user_id=user_id,
            role="user",
            content=request.query,
            parent_id=request.parent_id,
        )
        await link_attachments_to_message(
            request.attachment_ids, request.session_id, user_message["id"]
        )

        async def stream_and_persist():
            answer_parts: list[str] = []
            conversation_id: str | None = None
            response_parent_id = request.parent_id
            stream_error: str | None = None
            trace_events: list[dict[str, Any]] = []
            sources: list[dict[str, Any]] = []

            try:
                async for payload in token_stream:
                    if payload.get("conversation_id"):
                        conversation_id = payload["conversation_id"]
                    if payload.get("parent_id") is not None:
                        response_parent_id = payload["parent_id"]
                    if payload.get("type") == "delta" and payload.get("text"):
                        answer_parts.append(payload["text"])
                    elif payload.get("type") == "full" and payload.get("answer"):
                        answer_parts = [payload["answer"]]
                    elif payload.get("type") == "error":
                        stream_error = payload.get("message") or "生成失败"
                    elif payload.get("type") == "agent":
                        trace_events.append(payload)
                    elif payload.get("type") == "sources":
                        sources = list(payload.get("items") or [])
                    yield _encode_sse(payload)
            except LLMRateLimitError as exc:
                stream_error = str(exc)
                payload = {
                    "type": "error",
                    "code": exc.code,
                    "message": str(exc),
                    "retry_after": exc.retry_after,
                }
                yield _encode_sse(payload)
                yield _encode_sse({"type": "end"})
            except Exception:
                logger.exception("LangGraph Agent 执行失败")
                stream_error = "Agent 运行时暂时不可用，请稍后重试。"
                yield _encode_sse(
                    {"type": "error", "code": "agent_error", "message": stream_error}
                )
                yield _encode_sse({"type": "end"})

            content = "".join(answer_parts).strip()
            if not content and stream_error:
                content = stream_error

            if content:
                try:
                    await add_message(
                        session_id=request.session_id,
                        user_id=user_id,
                        role="assistant",
                        content=content,
                        conversation_id=conversation_id,
                        parent_id=response_parent_id,
                        status="error" if stream_error else "complete",
                        agent_trace=trace_events,
                        sources=sources,
                    )
                except Exception:
                    logger.exception("保存会话历史失败: session_id=%s", request.session_id)

        return StreamingResponse(
            stream_and_persist(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("处理请求时出错: %s", str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"处理请求时出错: {str(e)}",
        ) from e


def _encode_sse(payload: dict[str, Any]) -> str:
    """按照 SSE 协议编码单个 JSON 事件。"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.get("/conversation/{conversation_id}", response_model=DialogueNodeBase)
async def get_conversation(conversation_id: str):
    """
    获取对话树（从 Neo4j 查询）
    
    Args:
        conversation_id: 对话 ID（AI 节点 ID）
        
    Returns:
        对话树节点
    """
    user_id = ANONYMOUS_USER_ID
    
    try:
        tree = await neo4j_client.get_dialogue_tree(
            root_node_id=conversation_id,
            user_id=user_id
        )
        
        if not tree:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="对话不存在"
            )
        
        # 递归转换子节点
        def convert_node(node_dict: dict) -> DialogueNodeBase:
            """递归转换节点字典为 DialogueNodeBase"""
            children = []
            for child_dict in node_dict.get("children", []):
                children.append(convert_node(child_dict))
            
            return DialogueNodeBase(
                node_id=node_dict.get("node_id", ""),
                parent_id=None,  # 子节点的 parent_id 在 Neo4j 中通过关系维护
                user_id=node_dict.get("user_id", user_id),
                role=node_dict.get("role", "assistant"),
                content=node_dict.get("content", ""),
                intent=node_dict.get("intent"),
                mastery_score=node_dict.get("mastery_score", 0.0),
                timestamp=node_dict.get("timestamp"),
                children=children
            )
        
        # 转换为 DialogueNodeBase 格式
        return convert_node(tree)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查询对话树失败: {str(e)}",
        ) from e
