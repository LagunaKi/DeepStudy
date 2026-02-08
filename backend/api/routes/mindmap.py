"""
思维导图相关路由 (纯数据稳健版)
"""
import logging

from fastapi import APIRouter

from backend.api.schemas.response import MindMapGraph
from backend.data.neo4j_client import neo4j_client
from backend.data.profile_store import (
    ANONYMOUS_USER_ID,
    concept_normalizer,
    get_all_profiles,
)

# 配置日志
logger = logging.getLogger(__name__)


router = APIRouter(prefix="/mindmap", tags=["mindmap"])


@router.get("/{conversation_id}", response_model=MindMapGraph)
async def get_mind_map(conversation_id: str):
    """
    获取指定会话的思维导图数据，并融合学习画像信息。

    - 图结构来自 Neo4j 中的 DialogueNode + HAS_CHILD / HAS_KEYWORD 关系
    - 对于 type 为 root/keyword 的节点，尝试按概念名关联画像维度 (U, R, A, score, times)
    """
    logger.info("[MindMap Tree] 开始查询会话树: %s", conversation_id)
    
    # 修复：优先查找 _root 节点
    root_id = f"{conversation_id}_root"
    
    cypher = """
    // 1. 首先确定根节点（优先查找 _root 节点）
    OPTIONAL MATCH (root:DialogueNode)
    WHERE root.node_id = $root_id
    
    // 2. 如果没有找到 _root，则查找 conversation_id 节点并向上追溯到根节点
    OPTIONAL MATCH (ai_node:DialogueNode {node_id: $cid})
    OPTIONAL MATCH (ai_node)<-[:HAS_CHILD*0..5]-(parent:DialogueNode)
    WHERE NOT (parent)<-[:HAS_CHILD]-()  // 确保这是根节点（没有父节点）
    
    // 3. 合并所有可能的根节点来源
    WITH coalesce(root, parent, ai_node) as actual_root
    WHERE actual_root IS NOT NULL
    
    // 4. 从根节点开始，获取所有可达节点（使用递归模式）
    MATCH (actual_root)-[:HAS_CHILD|HAS_KEYWORD*0..10]-(connected_node:DialogueNode)
    WITH collect(DISTINCT connected_node) + collect(DISTINCT actual_root) as all_nodes_coll
    
    // 5. 展开所有节点并获取它们的关系
    UNWIND all_nodes_coll as node
    WITH collect(DISTINCT node) as all_nodes  // 去重
    UNWIND all_nodes as node
    OPTIONAL MATCH (node)-[r:HAS_CHILD|HAS_KEYWORD]->(child:DialogueNode)
    
    // 6. 返回所有节点及其子节点
    RETURN 
        node.node_id as source_id, 
        node.title as source_title, 
        node.content as source_content,
        node.type as source_type,
        
        child.node_id as target_id, 
        child.title as target_title,
        child.content as target_content,
        child.type as target_type,
        
        elementId(r) as rel_id,
        type(r) as rel_type
    """
    
    try:
        records = await neo4j_client.query(
            cypher,
            {"root_id": root_id, "cid": conversation_id},
        )
        logger.info("查询成功！共找到 %d 条记录", len(records))

        nodes_dict: dict = {}
        edges: list = []
        
        # 如果没有找到任何记录，可能节点还没保存，返回空
        if len(records) == 0:
            logger.warning(
                "未找到节点: conversation_id=%s, root_id=%s",
                conversation_id,
                root_id,
            )
            return MindMapGraph(nodes=[], edges=[])
        
        # 先添加根节点（即使没有子节点）
        root_found = False
        for record in records:
            s_id = record.get("source_id")
            if s_id and s_id not in nodes_dict:
                root_found = True
                label = (
                    record.get("source_title")
                    or record.get("source_content")
                    or "核心概念"
                )
                if len(label) > 15 and not record.get("source_title"):
                    label = label[:15] + "..."
                nodes_dict[s_id] = {
                    "id": s_id,
                    "type": "default",
                    "data": {
                        "label": label,
                        "type": record.get("source_type") or "root",
                    },
                }
        
        # 如果没有找到根节点，说明数据还没保存，返回空
        if not root_found:
            logger.warning("未找到根节点: conversation_id=%s", conversation_id)
            return MindMapGraph(nodes=[], edges=[])
        
        # 处理子节点和关系
        for record in records:
            s_id = record.get("source_id")
            t_id = record.get("target_id")
            r_id = record.get("rel_id")
            
            if not s_id:
                continue
            
            # 如果有子节点，处理子节点
            if t_id and r_id:
                if t_id not in nodes_dict:
                    label = (
                        record.get("target_title")
                        or record.get("target_content")
                        or "子节点"
                    )
                    if len(label) > 15 and not record.get("target_title"):
                        label = label[:15] + "..."
                    nodes_dict[t_id] = {
                        "id": t_id,
                        "type": "default",
                        "data": {
                            "label": label,
                            "type": record.get("target_type") or "keyword",
                        },
                    }
                
                edges.append(
                    {
                        "id": str(r_id),
                        "source": s_id,
                        "target": t_id,
                        "label": record.get("rel_type"),
                    },
                )

        # 融合学习画像：根据节点 label -> 规范概念名 -> 画像维度
        profiles = await get_all_profiles(user_id=ANONYMOUS_USER_ID)
        profile_map = {p.concept_key: p for p in profiles}

        for node in nodes_dict.values():
            data = node.get("data") or {}
            node_type = data.get("type")
            label = data.get("label") or ""
            # 仅对 root/keyword 类型节点尝试关联画像
            if node_type not in ("root", "keyword"):
                continue
            normalized = concept_normalizer.normalize(label)
            profile = profile_map.get(normalized)
            if not profile:
                continue
            last_ts = (
                profile.last_practice.isoformat()
                if profile.last_practice
                else None
            )
            data["profile"] = {
                "concept": profile.concept_key,
                "u": profile.u,
                "r": profile.r,
                "a": profile.a,
                "score": profile.score,
                "times": profile.times,
                "last_practice": last_ts,
            }
            node["data"] = data

        nodes_list = list(nodes_dict.values())
        logger.info("最终构建树: %d 个节点, %d 条连线", len(nodes_list), len(edges))
        
        return MindMapGraph(nodes=nodes_list, edges=edges)
        
    except Exception as exc:  # pragma: no cover - 降级处理
        logger.error("[MindMap Error] 查询失败: %s", exc, exc_info=True)
        return MindMapGraph(nodes=[], edges=[])
