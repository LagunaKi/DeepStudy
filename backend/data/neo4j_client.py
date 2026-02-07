import logging
from typing import List, Dict, Optional
from datetime import datetime
from neo4j import AsyncGraphDatabase
from neo4j.exceptions import (
    ServiceUnavailable, 
    AuthError, 
    ConstraintError,
    Neo4jError
)
from backend.config import settings

# 配置日志
logger = logging.getLogger("neo4j_client")
logging.basicConfig(level=logging.INFO)

class Neo4jClient:
    """Neo4j 客户端（整合版：包含基础功能、学习路径及对话记忆）"""
    
    def __init__(self):
        """初始化 Neo4j 客户端并建立连接池"""
        import os
        self._uri = settings.NEO4J_URI
        self._user = settings.NEO4J_USER
        self._password = settings.NEO4J_PASSWORD
        self.driver = None
        
        # 检查是否禁用认证（Docker 环境默认禁用）
        auth_disabled = os.environ.get("NEO4J_AUTH_DISABLED", "").lower() in ("true", "1", "yes")
        # 在 Docker 环境中默认禁用认证
        is_docker = os.path.exists("/.dockerenv") or os.path.exists("/mnt/workspace")
        
        try:
            if auth_disabled or is_docker:
                # 禁用认证模式：不传 auth 参数
                self.driver = AsyncGraphDatabase.driver(self._uri)
                logger.info(f"Neo4j driver initialized at {self._uri} (auth disabled)")
            else:
                # 启用认证模式
                self.driver = AsyncGraphDatabase.driver(
                    self._uri,
                    auth=(self._user, self._password)
                )
                logger.info(f"Neo4j driver initialized at {self._uri} (auth enabled)")
        except Exception as e:
            logger.error(f"Failed to initialize Neo4j driver: {e}")
            raise e

    async def verify_connectivity(self):
        """验证数据库连接是否可用"""
        try:
            await self.driver.verify_connectivity()
            logger.info("Neo4j connection verified successfully.")
        except (ServiceUnavailable, AuthError) as e:
            logger.error(f"Neo4j connection verification failed: {e}")
            raise

    async def close(self):
        """关闭连接"""
        if self.driver:
            await self.driver.close()
            logger.info("Neo4j driver closed.")
    
    # ==============================
    # 核心功能：通用查询 
    # ==============================
    async def query(self, cypher: str, parameters: dict = None):
        """
        执行通用 Cypher 查询 (支持返回列表)
        """
        if not self.driver:
            raise Exception("Neo4j driver not initialized")

        try:
            async with self.driver.session() as session:
                result = await session.run(cypher, parameters or {})
                # 异步迭代获取所有记录
                return [record async for record in result]
        except Exception as e:
            logger.error(f"Cypher Query Error: {e}")
            # 抛出异常以便上层处理（比如 Orchestrator 的降级逻辑）
            raise e

    # ==============================
    # 对话记忆与图谱构建 (MindMap 核心)
    # ==============================

    async def save_dialogue_node(
        self, 
        node_id: str, 
        user_id: str, 
        role: str, 
        content: str, 
        intent: Optional[str] = None, 
        mastery_score: float = 0.0, 
        timestamp: Optional[datetime] = None,
        title: Optional[str] = None,
        type: Optional[str] = "default"
    ) -> None:
        """保存对话/概念节点 (修复版：根据 type 动态打标签)"""
        if timestamp is None:
            timestamp = datetime.utcnow()
        
        if not title:
            title = content[:20] + "..." if len(content) > 20 else content

        # 根据 type 决定标签：如果是 concept 就打 :Concept 标签，否则打 :DialogueNode
        label = "Concept" if type == "concept" else "DialogueNode"

        async with self.driver.session() as session:
            # 使用 f-string 动态注入 Label (Cypher 不支持参数化 Label)
            # 注意：node_id 必须是唯一的
            await session.run(
                f"""
                MERGE (n:{label} {{node_id: $node_id}})
                SET n.user_id = $user_id,
                    n.role = $role,
                    n.content = $content,
                    n.intent = $intent,
                    n.mastery_score = $mastery_score,
                    n.timestamp = $timestamp,
                    n.title = $title,
                    n.type = $type
                """,
                node_id=node_id, 
                user_id=user_id, 
                role=role, 
                content=content,
                intent=intent, 
                mastery_score=mastery_score, 
                timestamp=timestamp.isoformat(),
                title=title,
                type=type
            )
    
    async def link_dialogue_nodes(self, parent_node_id: str, child_node_id: str, fragment_id: Optional[str] = None) -> None:
        """
        [修复版] 建立连接：移除标签限制，允许对话连知识、知识连知识
        """
        async with self.driver.session() as session:
            # ⭐ 核心修改：把 (n:DialogueNode) 改成 (n {node_id: ...})
            # 这样不管它是 DialogueNode 还是 Concept，只要 ID 对得上，就能连！
            query = """
                MATCH (parent {node_id: $parent_node_id})
                MATCH (child {node_id: $child_node_id})
                MERGE (parent)-[r:HAS_CHILD]->(child)
                SET r.fragment_id = $fragment_id
            """
            try:
                await session.run(query, parent_node_id=parent_node_id, child_node_id=child_node_id, fragment_id=fragment_id)
                logger.info(f"Link success: {parent_node_id} -> {child_node_id}")
            except Exception as e:
                logger.error(f"Link failed: {e}")

    async def get_ancestor_node_ids(self, node_id: str, max_depth: int = 6) -> List[str]:
        """
        从当前节点沿 HAS_CHILD 入边向上遍历，返回所有祖先的 node_id（不含当前节点）。
        方向为 (ancestor)-[:HAS_CHILD]->(child)，故从 child 找 ancestor。
        """
        if not node_id:
            return []
        async with self.driver.session() as session:
            result = await session.run(
                """
                MATCH (ancestor)-[:HAS_CHILD*1..%d]->(n {node_id: $node_id})
                RETURN DISTINCT ancestor.node_id AS id
                """ % max_depth,
                node_id=node_id,
            )
            records = await result.data()
        return [r["id"] for r in records if r.get("id")]

    async def get_dialogue_node(self, node_id: str) -> Optional[Dict]:
        """获取单个对话节点"""
        async with self.driver.session() as session:
            result = await session.run("MATCH (n:DialogueNode {node_id: $node_id}) RETURN n", node_id=node_id)
            record = await result.single()
            return dict(record["n"]) if record else None

    async def get_dialogue_tree(self, root_node_id: str, user_id: str, max_depth: int = 6) -> Optional[Dict]:
        """
        [智能修复版] 获取图谱：自动修正 ID 后缀，无视标签和方向，全量抓取
        """
        async with self.driver.session() as session:
            # =========================================================
            # 1. 智能 ID 匹配 (Smart ID Resolution)
            # 解决 Route 层可能乱加 _root 后缀导致查不到的问题
            # =========================================================
            potential_ids = [root_node_id]
            
            # 如果传入的有后缀，尝试去掉后缀
            if root_node_id.endswith("_root"):
                potential_ids.append(root_node_id.replace("_root", ""))
            # 如果传入的没后缀，尝试加上后缀 (兼容旧数据)
            else:
                potential_ids.append(f"{root_node_id}_root")
                
            actual_root_id = None
            root_record = None

            # 挨个试，哪个能查到就用哪个
            for pid in potential_ids:
                result = await session.run("MATCH (n {node_id: $id}) RETURN n", id=pid)
                root_record = await result.single()
                if root_record:
                    actual_root_id = pid
                    # logger.info(f"ID Hit: {pid} (Original: {root_node_id})")
                    break
            
            if not root_record:
                # logger.warning(f"MindMap lookup failed. Tried IDs: {potential_ids}")
                return None
            
            root_node = dict(root_record["n"])
            root_node["children"] = [] 

            # =========================================================
            # 2. 万能递归查询 (Universal Traversal)
            # 从找到的 actual_root_id 开始，抓取所有连通子图
            # =========================================================
            query = """
                MATCH (root {node_id: $root_id})
                MATCH path = (root)-[*0..6]-(node)
                WHERE node.node_id IS NOT NULL 
                RETURN path
            """
            
            result = await session.run(query, root_id=actual_root_id)
            
            # 3. 内存组装树结构
            nodes_map = {actual_root_id: root_node}
            
            async for record in result:
                path = record["path"]
                for rel in path.relationships:
                    # 处理节点对象
                    start_node = dict(rel.start_node)
                    end_node = dict(rel.end_node)
                    
                    # 注册节点到 map
                    for n in [start_node, end_node]:
                        # 优先用 node_id，没有则用 name，再没有则用 element_id
                        if "node_id" not in n:
                            n["node_id"] = n.get("name", str(n.element_id if hasattr(n, 'element_id') else n.id))
                        
                        if n["node_id"] not in nodes_map:
                            n["children"] = []
                            # 默认样式处理
                            if "type" not in n: n["type"] = "keyword"
                            nodes_map[n["node_id"]] = n

                    # 建立父子连接
                    s_id = start_node["node_id"]
                    e_id = end_node["node_id"]
                    
                    if s_id in nodes_map and e_id in nodes_map:
                        parent = nodes_map[s_id]
                        child = nodes_map[e_id]
                        
                        # 简单防重：避免 A->B 和 B->A 导致无限循环
                        # 这里我们只做单纯的 append，前端 ReactFlow 会处理好布局
                        if not any(c["node_id"] == e_id for c in parent["children"]):
                            parent["children"].append(child)

            return nodes_map[actual_root_id]
        
    # ==============================
    # 辅助功能 (供兼容旧代码)
    # ==============================

    async def create_node(self, label: str, properties: Dict) -> Optional[str]:
        """创建节点"""
        query = f"CREATE (n:{label} $properties) RETURN n.node_id as node_id"
        try:
            async with self.driver.session() as session:
                result = await session.run(query, properties=properties)
                record = await result.single()
                # 优先返回 node_id 属性，如果没有则返回 None
                return str(record["node_id"]) if record and "node_id" in record else None
        except Exception as e:
            logger.error(f"Error creating node {label}: {e}")
            raise

    async def create_relationship(
        self, source_id: str, target_id: str, relation_type: str, properties: Optional[Dict] = None
    ) -> bool:
        """创建关系 (基于 node_id 属性)"""
        # 这里逻辑必须改成匹配 node_id 属性，而不是内部 id
        query_base = f"MATCH (a), (b) WHERE a.node_id = $source_id AND b.node_id = $target_id"
        create_part = f"CREATE (a)-[r:{relation_type} $properties]->(b)" if properties else f"CREATE (a)-[r:{relation_type}]->(b)"
        query = f"{query_base} {create_part}"

        try:
            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    source_id=source_id, 
                    target_id=target_id, 
                    properties=properties or {}
                )
                summary = await result.consume()
                return summary.counters.relationships_created > 0
        except Exception as e:
            logger.error(f"Error creating relationship: {e}")
            return False

    async def get_node_by_name(self, label: str, name: str) -> Optional[Dict]:
        """根据名称获取节点"""
        query = f"MATCH (n:{label} {{name: $name}}) RETURN n"
        try:
            async with self.driver.session() as session:
                result = await session.run(query, name=name)
                record = await result.single()
                return dict(record["n"]) if record else None
        except Exception as e:
            logger.error(f"Error in get_node_by_name: {e}")
            return None

    async def get_learning_path(self, target_concept_name: str) -> List[str]:
        """查找学习路径"""
        query = """
        MATCH (target:Concept {name: $name})
        MATCH path = (target)-[:REQUIRES|PART_OF*]->(root)
        WHERE NOT (root)-[:REQUIRES|PART_OF]->()
        RETURN reverse([node in nodes(path) | node.name]) AS steps
        LIMIT 1
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(query, name=target_concept_name)
                record = await result.single()
                return record["steps"] if record else []
        except Exception as e:
            logger.error(f"Error finding learning path: {e}")
            return []
# 全局客户端实例
neo4j_client = Neo4jClient()