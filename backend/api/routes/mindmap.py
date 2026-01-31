"""
思维导图相关路由 (纯数据稳健版)
"""
from fastapi import APIRouter, Depends
from backend.api.schemas.response import MindMapGraph
from backend.api.middleware.auth import get_current_user_id
from backend.data.neo4j_client import neo4j_client
import logging

# 配置日志
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mindmap", tags=["mindmap"])

@router.get("/{conversation_id}", response_model=MindMapGraph)
async def get_mind_map(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id)
):
    logger.info(f"[MindMap Tree] 开始查询会话树: {conversation_id}")
    
    # 修复：使用 CONCAT 函数，并优先查找 _root 节点
    # 构建 root_id：conversation_id + "_root"
    root_id = f"{conversation_id}_root"
    
    cypher = """
    // 1. 优先查找根节点（_root 后缀）
    MATCH (root:DialogueNode)
    WHERE root.node_id = $root_id
    
    // 2. 如果找不到 _root，则查找 conversation_id 节点并向上找父节点
    OPTIONAL MATCH (ai_node:DialogueNode {node_id: $cid})
    OPTIONAL MATCH (ai_node)<-[:HAS_CHILD|HAS_KEYWORD]-(parent:DialogueNode)
    WITH coalesce(root, parent, ai_node) as actual_root
    
    // 3. 查找根节点的所有子节点和关系（使用 OPTIONAL MATCH 确保即使没有子节点也返回根节点）
    OPTIONAL MATCH (actual_root)-[r:HAS_CHILD|HAS_KEYWORD]->(child:DialogueNode)
    
    // 4. 返回根节点和所有子节点（即使没有子节点也返回根节点）
    RETURN 
        actual_root.node_id as source_id, 
        actual_root.title as source_title, 
        actual_root.content as source_content,
        actual_root.type as source_type,
        
        child.node_id as target_id, 
        child.title as target_title,
        child.content as target_content,
        child.type as target_type,
        
        elementId(r) as rel_id,
        type(r) as rel_type
    """
    
    try:
        records = await neo4j_client.query(cypher, {"root_id": root_id, "cid": conversation_id})
        logger.info(f"查询成功！共找到 {len(records)} 条记录")

        nodes_dict = {}
        edges = []
        
        # 如果没有找到任何记录，可能节点还没保存，返回空
        if len(records) == 0:
            logger.warning(f"未找到节点: conversation_id={conversation_id}, root_id={root_id}")
            return MindMapGraph(nodes=[], edges=[])
        
        # 先添加根节点（即使没有子节点）
        root_found = False
        for record in records:
            s_id = record.get('source_id')
            if s_id and s_id not in nodes_dict:
                root_found = True
                label = record.get('source_title') or record.get('source_content') or "核心概念"
                if len(label) > 15 and not record.get('source_title'): 
                    label = label[:15] + "..."
                nodes_dict[s_id] = {
                    "id": s_id,
                    "type": "default", 
                    "data": { 
                        "label": label,
                        "type": record.get('source_type') or 'root'
                    }
                }
        
        # 如果没有找到根节点，说明数据还没保存，返回空
        if not root_found:
            logger.warning(f"未找到根节点: conversation_id={conversation_id}")
            return MindMapGraph(nodes=[], edges=[])
        
        # 处理子节点和关系
        for record in records:
            s_id = record.get('source_id')
            t_id = record.get('target_id')
            r_id = record.get('rel_id')
            
            if not s_id:
                continue
            
            # 如果有子节点，处理子节点
            if t_id and r_id:
                if t_id not in nodes_dict:
                    label = record.get('target_title') or record.get('target_content') or "子节点"
                    if len(label) > 15 and not record.get('target_title'): 
                        label = label[:15] + "..."
                    nodes_dict[t_id] = {
                        "id": t_id,
                        "type": "default",
                        "data": { 
                            "label": label,
                            "type": record.get('target_type') or 'keyword'
                        }
                    }
                
                edges.append({
                    "id": str(r_id),
                    "source": s_id,
                    "target": t_id,
                    "label": record.get('rel_type')
                })

        nodes_list = list(nodes_dict.values())
        logger.info(f"最终构建树: {len(nodes_list)} 个节点, {len(edges)} 条连线")
        
        return MindMapGraph(nodes=nodes_list, edges=edges)
        
    except Exception as e:
        logger.error(f"[MindMap Error] 查询失败: {e}", exc_info=True)
        return MindMapGraph(nodes=[], edges=[])
