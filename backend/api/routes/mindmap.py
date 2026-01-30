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
    print(f"\n======== [MindMap Tree] 开始查询会话树: {conversation_id} ========")
    
    # 👇 核心改动：直接返回属性字符串，不返回 Node/Relationship 对象
    # 这样避免了对象解析的任何歧义
    cypher = """
    MATCH (n:DialogueNode)
    WHERE n.node_id = $cid OR n.node_id = $cid + "_root"
    
    // 1. 向上找 Root
    OPTIONAL MATCH (n)<-[:HAS_CHILD|HAS_KEYWORD]-(parent)
    WITH coalesce(parent, n) as root
    
    // 2. 向下找所有连线和子节点
    MATCH (root)-[r]->(child)
    
    // 3. 直接返回属性 (解耦对象)
    RETURN 
        root.node_id as source_id, 
        root.title as source_title, 
        root.content as source_content,
        root.type as source_type,
        
        child.node_id as target_id, 
        child.title as target_title,
        child.content as target_content,
        child.type as target_type,
        
        elementId(r) as rel_id,
        type(r) as rel_type
    """
    
    try:
        records = await neo4j_client.query(cypher, {"cid": conversation_id})
        print(f"查询成功！共找到 {len(records)} 条记录")

        nodes_dict = {}
        edges = []
        
        for i, record in enumerate(records):
            # 直接取字符串，这绝对是 Truthy 的
            s_id = record['source_id']
            t_id = record['target_id']
            r_id = record['rel_id']
            
            # 打印调试，看看到底缺不缺
            if not s_id or not t_id or not r_id:
                print(f"⚠️ 第 {i} 条记录数据缺失: Source={s_id}, Target={t_id}, Rel={r_id}")
                continue

            # --- 1. 处理源节点 (Root) ---
            if s_id not in nodes_dict:
                # 优先用 title，没有就用 content 截断
                label = record['source_title'] or record['source_content'] or "核心概念"
                if len(label) > 15 and not record['source_title']: label = label[:15] + "..."
                
                nodes_dict[s_id] = {
                    "id": s_id,
                    "type": "default", 
                    "data": { 
                        "label": label,
                        "type": record['source_type'] or 'root'
                    }
                }
            
            # --- 2. 处理目标节点 (Child) ---
            if t_id not in nodes_dict:
                label = record['target_title'] or record['target_content'] or "子节点"
                if len(label) > 15 and not record['target_title']: label = label[:15] + "..."

                nodes_dict[t_id] = {
                    "id": t_id,
                    "type": "default",
                    "data": { 
                        "label": label,
                        "type": record['target_type'] or 'keyword'
                    }
                }

            # --- 3. 处理连线 (Edge) ---
            # 只要 s_id 和 t_id 都处理好了，连线直接加！
            edges.append({
                "id": str(r_id), # 确保是字符串
                "source": s_id,
                "target": t_id,
                "label": record['rel_type']
            })

        # 转换为列表
        nodes_list = list(nodes_dict.values())
        print(f"最终构建树: {len(nodes_list)} 个节点, {len(edges)} 条连线")
        
        return MindMapGraph(nodes=nodes_list, edges=edges)
        
    except Exception as e:
        print(f"❌ [MindMap Error] 查询失败: {e}")
        import traceback
        traceback.print_exc()
        return MindMapGraph(nodes=[], edges=[])