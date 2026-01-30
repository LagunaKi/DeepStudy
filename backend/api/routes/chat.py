"""
聊天相关路由
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from backend.api.schemas.request import ChatRequest
from backend.api.schemas.response import DialogueNodeBase
from backend.api.middleware.auth import get_current_user_id
from backend.agent.orchestrator import AgentOrchestrator
from backend.data.neo4j_client import neo4j_client

# 配置日志
logger = logging.getLogger(__name__)


router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("")
async def chat(
    request: ChatRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    发送聊天消息（支持普通提问和划词追问），使用 HTTP 流式返回结果。
    """
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

        # 暂时对普通提问走流式，对划词追问走非流式一次性返回
        if request.ref_fragment_id:
            logger.info("处理划词追问（非流式）...")
            response = await orchestrator.process_recursive_query(
                user_id=user_id,
                parent_id=request.parent_id or "",
                fragment_id=request.ref_fragment_id,
                query=request.query,
            )
            logger.info("递归追问处理完成，conversation_id=%s", response.conversation_id)
            # 为兼容前端流式消费，这里也返回单条 JSON 行
            async def single_chunk():
                import json as _json

                payload = {
                    "type": "full",
                    "answer": response.answer,
                    "conversation_id": response.conversation_id,
                    "parent_id": response.parent_id,
                }
                yield _json.dumps(payload, ensure_ascii=False) + "\n"

            return StreamingResponse(single_chunk(), media_type="application/json")

        logger.info("处理普通提问（流式）...")
        token_stream = orchestrator.process_query_stream(
            user_id=user_id,
            query=request.query,
            parent_id=request.parent_id,
            session_id=request.session_id,
        )

        return StreamingResponse(token_stream, media_type="application/json")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("处理请求时出错: %s", str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"处理请求时出错: {str(e)}",
        )


@router.get("/conversation/{conversation_id}", response_model=DialogueNodeBase)
async def get_conversation(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """
    获取对话树（从 Neo4j 查询）
    
    Args:
        conversation_id: 对话 ID（AI 节点 ID）
        user_id: 当前用户 ID
        
    Returns:
        对话树节点
    """
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
            detail=f"查询对话树失败: {str(e)}"
        )
