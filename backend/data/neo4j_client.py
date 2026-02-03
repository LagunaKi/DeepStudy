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
        title: Optional[str] = None,   # 用于图谱显示的短标题
        type: Optional[str] = "default" # 节点类型 (root, keyword, default)
    ) -> None:
        """保存对话节点 (支持 MindMap 扩展属性)"""
        if timestamp is None:
            timestamp = datetime.utcnow()
        
        # 如果没有传 title，默认截取 content 的前20个字
        if not title:
            title = content[:20] + "..." if len(content) > 20 else content
        async with self.driver.session() as session:
            await session.run(
                """
                MERGE (n:DialogueNode {node_id: $node_id})
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
        """创建对话节点之间的父子关系"""
        async with self.driver.session() as session:
            # 使用 node_id 属性匹配，而不是内部 id()
            query = """
                MATCH (parent:DialogueNode {node_id: $parent_node_id})
                MATCH (child:DialogueNode {node_id: $child_node_id})
                MERGE (parent)-[r:HAS_CHILD]->(child)
                SET r.fragment_id = $fragment_id
            """
            await session.run(query, parent_node_id=parent_node_id, child_node_id=child_node_id, fragment_id=fragment_id)

    async def get_dialogue_node(self, node_id: str) -> Optional[Dict]:
        """获取单个对话节点"""
        async with self.driver.session() as session:
            result = await session.run("MATCH (n:DialogueNode {node_id: $node_id}) RETURN n", node_id=node_id)
            record = await result.single()
            return dict(record["n"]) if record else None

    async def get_dialogue_tree(self, root_node_id: str, user_id: str, max_depth: int = 10) -> Optional[Dict]:
        """获取对话树（递归查询）"""
        async with self.driver.session() as session:
            root_result = await session.run(
                "MATCH (n:DialogueNode {node_id: $node_id, user_id: $user_id}) RETURN n",
                node_id=root_node_id, user_id=user_id
            )
            root_record = await root_result.single()
            if not root_record:
                return None
            
            root_node = dict(root_record["n"])
            
            async def get_children(parent_id: str, depth: int) -> List[Dict]:
                if depth >= max_depth: return []
                # 查询子节点时也使用 node_id
                result = await session.run(
                    "MATCH (parent:DialogueNode {node_id: $parent_id})-[:HAS_CHILD]->(child:DialogueNode) RETURN child ORDER BY child.timestamp",
                    parent_id=parent_id
                )
                children = []
                async for record in result:
                    child_node = dict(record["child"])
                    if child_node.get("node_id"):
                        child_node["children"] = await get_children(child_node["node_id"], depth + 1)
                        children.append(child_node)
                return children
            
            root_node["children"] = await get_children(root_node_id, 0)
            return root_node

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