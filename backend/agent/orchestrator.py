"""
Agent 编排器
使用自定义 LLM 客户端编排对话流程
"""
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime

from backend.agent.activity_classifier import classify_activity
from backend.agent.concept_extractor import extract_concept_structure
from backend.agent.extractors import knowledge_extractor
from backend.agent.intent_router import IntentRouter, IntentType
from backend.agent.llm_client import GeminiLLMClient, LLMRateLimitError
from backend.agent.prompts.system_prompts import (
    RECURSIVE_ANSWER_QUERY_ONLY,
    RECURSIVE_ANSWER_WITH_CONTEXT,
    RECURSIVE_ANSWER_WITH_SELECTION,
    RECURSIVE_PROMPT,
)
from backend.agent.strategies import CodeStrategy, ConceptStrategy, DerivationStrategy
from backend.api.schemas.response import AgentResponse
from backend.config import settings
from backend.data.neo4j_client import neo4j_client
from backend.data.profile_store import (
    ActivityVector,
    apply_learning_event_to_concepts,
)

# 配置日志
logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """
    Agent 编排器
    负责协调意图识别、策略选择和响应生成
    """

    def __init__(self):
        """初始化编排器"""
        logger.info("开始初始化 Orchestrator...")

        logger.info("初始化主模型: %s", settings.LLM_MODEL)
        self.llm = GeminiLLMClient(
            model_name=settings.LLM_MODEL,
            api_key=settings.GEMINI_API_KEY,
            thinking_level=settings.GEMINI_THINKING_LEVEL,
            min_request_interval_seconds=settings.GEMINI_MIN_REQUEST_INTERVAL_SECONDS,
        )
        logger.info("主模型初始化成功")

        logger.info("初始化 Coder 模型: %s", settings.LLM_CODER_MODEL)
        self.coder_llm = GeminiLLMClient(
            model_name=settings.LLM_CODER_MODEL,
            api_key=settings.GEMINI_API_KEY,
            thinking_level=settings.GEMINI_THINKING_LEVEL,
            min_request_interval_seconds=settings.GEMINI_MIN_REQUEST_INTERVAL_SECONDS,
        )
        logger.info("Coder 模型初始化成功")

        # 初始化意图路由器
        logger.info("初始化意图路由器...")
        self.intent_router = IntentRouter(self.llm)

        # 初始化策略
        logger.info("初始化策略...")
        self.strategies = {
            IntentType.DERIVATION: DerivationStrategy(self.llm),
            IntentType.CODE: CodeStrategy(self.coder_llm),
            IntentType.CONCEPT: ConceptStrategy(self.llm),
        }
        logger.info("Orchestrator 初始化完成")

    async def process_query(
        self,
        user_id: str,
        query: str,
        parent_id: str | None = None,
        session_id: str | None = None,
    ) -> AgentResponse:
        """
        处理用户查询（非流式路径，保留以兼容旧逻辑）
        """
        logger.info(f"开始处理查询: query={query[:50]}...")
        # 识别意图
        logger.info("识别意图...")
        intent = await self.intent_router.route(query)
        logger.info(f"识别结果: {intent.value}")

        # 选择策略
        logger.info(f"选择策略: {intent.value}")
        strategy = self.strategies[intent]

        # 处理查询
        logger.info("调用策略处理查询...")
        context = {
            "user_id": user_id,
            "parent_id": parent_id,
        }
        response = await strategy.process(query, context)
        logger.info("策略处理完成")

        # 提取知识三元组
        logger.info("提取知识三元组...")
        try:
            knowledge_triples = knowledge_extractor.extract_triples(response.answer)
            response.knowledge_triples = knowledge_triples
            logger.info(f"成功提取 {len(knowledge_triples)} 个知识三元组")
        except Exception as e:
            logger.warning(f"知识三元组提取失败: {str(e)}", exc_info=True)
            response.knowledge_triples = []

        # 生成对话 ID
        conversation_id = str(uuid.uuid4())
        response.conversation_id = conversation_id
        response.parent_id = parent_id
        logger.info(f"生成对话 ID: {conversation_id}")

        # 保存到 Neo4j（降级模式：失败只记录日志，不阻断返回）
        logger.info("开始保存到 Neo4j...")
        try:
            # 创建用户节点
            user_node_id = f"{conversation_id}_user"
            await neo4j_client.save_dialogue_node(
                node_id=user_node_id,
                user_id=user_id,
                role="user",
                content=query,
                intent=intent.value if intent else None,
            )

            # 创建 AI 节点
            ai_node_id = conversation_id
            await neo4j_client.save_dialogue_node(
                node_id=ai_node_id,
                user_id=user_id,
                role="assistant",
                content=response.answer,
                intent=intent.value if intent else None,
            )

            # 创建用户到 AI 的关系
            await neo4j_client.link_dialogue_nodes(
                parent_node_id=user_node_id,
                child_node_id=ai_node_id,
            )

            # 如果有父节点，创建父节点到用户节点的关系
            if parent_id:
                logger.info(f"创建父节点关系: parent_id={parent_id}")
                await neo4j_client.link_dialogue_nodes(
                    parent_node_id=parent_id,
                    child_node_id=user_node_id,
                )
            logger.info("Neo4j 保存成功")
        except Exception as e:
            # 降级：只记录错误，不中断主流程
            logger.warning(
                "保存对话到 Neo4j 失败（已降级处理，不影响主流程）: %s", str(e), exc_info=True
            )

        return response

    async def process_query_stream(
        self,
        user_id: str,
        query: str,
        parent_id: str | None = None,
        session_id: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        处理用户查询（流式输出 + 知识提炼）
        
        返回一个异步生成器，按行输出 JSON 字符串：
        - 第一行: {"type":"meta","conversation_id":...}
        - 后续多行: {"type":"delta","text":...}
        - 结束行: {"type":"end"}
        """
        logger.info(f"[stream] 开始处理查询: query={query[:50]}...")
        
        # 1. 获取父对话上下文（如果存在）
        parent_context = ""
        if parent_id:
            try:
                logger.info(f"[stream] 获取父对话上下文: parent_id={parent_id}")
                parent_node = await neo4j_client.get_dialogue_node(parent_id)
                if parent_node and parent_node.get('content'):
                    parent_context = parent_node['content']
                    logger.info(f"[stream] 成功获取父对话上下文，长度: {len(parent_context)}")
                else:
                    logger.warning("[stream] 无法获取父对话上下文，节点不存在或内容为空")
            except Exception as e:
                logger.warning(f"[stream] 获取父对话上下文失败: {str(e)}")

        # 2. 意图识别
        intent = await self.intent_router.route(query)
        logger.info(f"[stream] 识别结果: {intent.value}")

        strategy = self.strategies[intent]
        context = {
            "user_id": user_id,
            "parent_id": parent_id,
            "parent_context": parent_context,  # 新增：父对话内容
        }

        # 生成对话 ID，并提前下发给前端
        conversation_id = str(uuid.uuid4())
        logger.info(f"[stream] 生成对话 ID: {conversation_id}")

        # 缓存完整回答，用于流结束后写入 Neo4j
        answer_parts: list[str] = []

        # 首包：meta 信息
        yield json.dumps(
            {
                "type": "meta",
                "conversation_id": conversation_id,
                "parent_id": parent_id,
            },
            ensure_ascii=False,
        ) + "\n"

        try:
            # 2. 流式生成回答
            async for delta in strategy.process_stream(query, context):
                if not delta:
                    continue
                answer_parts.append(delta)
                yield json.dumps({"type": "delta", "text": delta}, ensure_ascii=False) + "\n"
        except LLMRateLimitError as e:
            logger.warning("[stream] Gemini 免费层限流: retry_after=%s", e.retry_after)
            yield json.dumps(
                {
                    "type": "error",
                    "code": e.code,
                    "message": str(e),
                    "retry_after": e.retry_after,
                },
                ensure_ascii=False,
            ) + "\n"
        except Exception as e:
            logger.error("[stream] LLM 流式生成失败: %s", str(e), exc_info=True)
            yield json.dumps(
                {
                    "type": "error",
                    "code": "model_error",
                    "message": "模型服务暂时不可用，请稍后重试。",
                },
                ensure_ascii=False,
            ) + "\n"
        finally:
            # 结束标记
            yield json.dumps({"type": "end"}, ensure_ascii=False) + "\n"

        # ==========================================
        # 3. 后处理：知识提取和知识图谱构建（异步，不阻塞前端）
        # ==========================================
        full_answer = "".join(answer_parts)
        
        if not full_answer:
            return

        # 在后台异步处理知识提取和图谱构建（降级模式）
        import asyncio
        asyncio.create_task(self._post_process_stream_response(
            conversation_id=conversation_id,
            user_id=user_id,
            query=query,
            full_answer=full_answer,
            intent=intent,
            parent_id=parent_id
        ))

    async def _post_process_stream_response(
        self,
        conversation_id: str,
        user_id: str,
        query: str,
        full_answer: str,
        intent: IntentType,
        parent_id: str | None = None,
    ):
        """
        流式回答的后处理：本地概念提取 + 学习画像更新 + Neo4j 保存
        """
        logger.info("[stream] 开始后处理：知识提取、画像更新和图谱构建...")
        
        try:
            # A. 提取知识三元组（当前主要用于日志与后续扩展）
            logger.info("[stream] 提取知识三元组...")
            try:
                knowledge_triples = knowledge_extractor.extract_triples(full_answer)
                logger.info(f"[stream] 成功提取 {len(knowledge_triples)} 个知识三元组")
            except Exception as e:
                logger.warning(f"[stream] 知识三元组提取失败: {str(e)}", exc_info=True)
                knowledge_triples = []

            # B. 本地概念提取 + 学习画像更新
            learning_delta = ActivityVector(0.0, 0.0, 0.0)
            try:
                structure = extract_concept_structure(query, full_answer)
                root_label = structure.get("root", "核心概念")
                children = structure.get("children", []) or []
                
                logger.info("[stream] 本地概念提取成功: Root=%s, Children=%s", root_label, children)

                # 将本轮涉及的概念应用为一次学习事件（活动类型由分类器判别，失败兜底 explain）
                raw_concepts = [root_label] + list(children)
                activity = await classify_activity(
                    self.llm, query, full_answer[:300] if full_answer else None
                )
                if activity is None:
                    activity = "explain"
                learning_delta = await apply_learning_event_to_concepts(
                    raw_concepts=raw_concepts,
                    activity=activity,
                    user_id=user_id,
                    conversation_id=conversation_id,
                )
                node_mastery_score = (learning_delta.u + learning_delta.r + learning_delta.a) / 3.0

                # 使用概念提取结果保存到 Neo4j
                user_node_id = f"{conversation_id}_root"
                await neo4j_client.save_dialogue_node(
                    node_id=user_node_id,
                    user_id=user_id,
                    role="user",
                    content=query,
                    intent=intent.value if intent else None,
                    title=root_label,
                    type="root",
                    mastery_score=node_mastery_score,
                )

                ai_node_id = conversation_id
                await neo4j_client.save_dialogue_node(
                    node_id=ai_node_id,
                    user_id=user_id,
                    role="assistant",
                    content=full_answer,
                    intent=intent.value if intent else None,
                    title="详细解释",
                    type="explanation",
                    mastery_score=node_mastery_score,
                )
                await neo4j_client.link_dialogue_nodes(user_node_id, ai_node_id)
                
                # 保存子概念
                for child_concept in children:
                    child_id = str(uuid.uuid4())
                    await neo4j_client.query(
                        """
                        MATCH (root:DialogueNode {node_id: $root_id})
                        CREATE (child:DialogueNode {
                            node_id: $child_id,
                            user_id: $user_id,
                            content: $name,
                            title: $name,
                            type: 'keyword',
                            timestamp: datetime()
                        })
                        CREATE (root)-[:HAS_KEYWORD]->(child)
                        """,
                        {
                            "root_id": user_node_id,
                            "child_id": child_id,
                            "user_id": user_id,
                            "name": child_concept,
                            "timestamp": datetime.now().isoformat(),
                        },
                    )

                logger.info("[stream] 知识图谱构建与画像更新完成")
                
            except Exception as e:
                logger.warning(
                    "[stream] 概念提取或画像更新失败，降级到基本保存: %s",
                    str(e),
                    exc_info=True,
                )
                # 降级：使用基本保存方式（不依赖概念提取）
                user_node_id = f"{conversation_id}_user"
                await neo4j_client.save_dialogue_node(
                    node_id=user_node_id,
                    user_id=user_id,
                    role="user",
                    content=query,
                    intent=intent.value if intent else None,
                )

                ai_node_id = conversation_id
                await neo4j_client.save_dialogue_node(
                    node_id=ai_node_id,
                    user_id=user_id,
                    role="assistant",
                    content=full_answer,
                    intent=intent.value if intent else None,
                )

                await neo4j_client.link_dialogue_nodes(
                    parent_node_id=user_node_id,
                    child_node_id=ai_node_id,
                )

                if parent_id:
                    await neo4j_client.link_dialogue_nodes(
                        parent_node_id=parent_id,
                        child_node_id=user_node_id,
                    )
                
        except Exception as e:
            logger.warning(
                "[stream] 后处理失败（已降级处理，不影响主流程）: %s",
                str(e),
                exc_info=True,
            )

    async def process_recursive_query_stream(
        self,
        user_id: str,
        parent_id: str,
        fragment_id: str,
        query: str,
        selected_text: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        处理递归追问（流式输出）
        
        返回一个异步生成器，按行输出 JSON 字符串：
        - 第一行: {"type":"meta","conversation_id":...}
        - 后续多行: {"type":"delta","text":...}
        - 结束行: {"type":"end"}
        """
        logger.info(f"[stream] 开始处理递归追问: fragment_id={fragment_id}, query={query[:50]}...")
        
        # 获取父对话上下文
        parent_context = ""
        try:
            logger.info(f"[stream] 获取父对话上下文: parent_id={parent_id}")
            parent_node = await neo4j_client.get_dialogue_node(parent_id)
            if parent_node and parent_node.get('content'):
                parent_context = parent_node['content']
                logger.info(f"[stream] 成功获取父对话上下文，长度: {len(parent_context)}")
            else:
                logger.warning("[stream] 无法获取父对话上下文，使用默认提示词")
        except Exception as e:
            logger.warning(f"[stream] 获取父对话上下文失败: {str(e)}")

        # 生成对话 ID
        conversation_id = str(uuid.uuid4())
        logger.info(f"[stream] 生成对话 ID: {conversation_id}")

        # 首包：meta 信息
        yield json.dumps(
            {
                "type": "meta",
                "conversation_id": conversation_id,
                "parent_id": parent_id,
            },
            ensure_ascii=False,
        ) + "\n"

        # 构建提示词
        parent_snippet = (parent_context[:500] + "...") if parent_context else ""
        if parent_context and selected_text:
            prompt = RECURSIVE_ANSWER_WITH_SELECTION.format(
                recursive_prompt=RECURSIVE_PROMPT,
                parent_context=parent_snippet,
                selected_text=selected_text,
                query=query,
            )
        elif parent_context:
            prompt = RECURSIVE_ANSWER_WITH_CONTEXT.format(
                recursive_prompt=RECURSIVE_PROMPT,
                parent_context=parent_snippet,
                query=query,
            )
        else:
            prompt = RECURSIVE_ANSWER_QUERY_ONLY.format(
                recursive_prompt=RECURSIVE_PROMPT,
                query=query,
            )

        # 缓存完整回答，用于流结束后写入 Neo4j
        answer_parts: list[str] = []

        try:
            # 流式生成回答
            logger.info("[stream] 调用 LLM 流式生成回答...")
            async for delta in self.llm.astream(prompt):
                if not delta:
                    continue
                answer_parts.append(delta)
                yield json.dumps({"type": "delta", "text": delta}, ensure_ascii=False) + "\n"
            logger.info("[stream] LLM 流式生成完成")
        except LLMRateLimitError as e:
            logger.warning("[stream] Gemini 免费层限流: retry_after=%s", e.retry_after)
            yield json.dumps(
                {
                    "type": "error",
                    "code": e.code,
                    "message": str(e),
                    "retry_after": e.retry_after,
                },
                ensure_ascii=False,
            ) + "\n"
        except Exception as e:
            logger.error("[stream] LLM 流式生成失败: %s", str(e), exc_info=True)
            yield json.dumps(
                {
                    "type": "error",
                    "code": "model_error",
                    "message": "模型服务暂时不可用，请稍后重试。",
                },
                ensure_ascii=False,
            ) + "\n"
        finally:
            # 结束标记
            yield json.dumps({"type": "end"}, ensure_ascii=False) + "\n"

        # 后处理：知识提取和 Neo4j 保存（异步，不阻塞前端）
        full_answer = "".join(answer_parts)
        if not full_answer:
            return

        import asyncio
        asyncio.create_task(self._post_process_recursive_query(
            conversation_id=conversation_id,
            user_id=user_id,
            query=query,
            full_answer=full_answer,
            parent_id=parent_id
        ))

    async def _post_process_recursive_query(
        self,
        conversation_id: str,
        user_id: str,
        query: str,
        full_answer: str,
        parent_id: str,
    ):
        """
        [完美缝合版] 递归追问后处理：
        1. 本地概念提取
        2. 画像更新 (更新学习状态)
        3. 图谱构建 (显式创建 _root 节点供前端渲染)
        """
        logger.info("[stream] 开始后处理递归追问：概念提取、画像更新与图谱构建...")
        
        try:
            # 1. 本地提取学习地图概念，避免后台再次消耗 Gemini 每日额度。
            structure = extract_concept_structure(query, full_answer)
            root_label = str(structure.get("root", "")).strip()
            children = structure.get("children") or []
            concepts = [root_label, *children] if root_label else list(children)

            # =====================================================
            # 2. 更新学习画像并计算分数
            # =====================================================
            node_mastery_score = 0.0
            try:
                activity = await classify_activity(
                    self.llm, query, full_answer[:300] if full_answer else None
                )
                if activity is None:
                    activity = "explain"
                
                learning_delta = await apply_learning_event_to_concepts(
                    raw_concepts=concepts,
                    activity=activity,
                    user_id=user_id,
                    conversation_id=conversation_id,
                )
                node_mastery_score = (learning_delta.u + learning_delta.r + learning_delta.a) / 3.0
            except Exception as e:
                logger.warning(f"[stream] 画像更新失败: {e}")

            # =====================================================
            # 3. 保存基础对话结构 (User -> AI)
            # =====================================================
            user_node_id = f"{conversation_id}_user"
            ai_node_id = conversation_id

            await neo4j_client.save_dialogue_node(
                node_id=user_node_id,
                user_id=user_id,
                role="user",
                content=query,
                intent="recursive",
                mastery_score=node_mastery_score,
            )

            await neo4j_client.save_dialogue_node(
                node_id=ai_node_id,
                user_id=user_id,
                role="assistant",
                content=full_answer,
                intent="recursive",
                type="explanation",
                mastery_score=node_mastery_score,
            )

            await neo4j_client.link_dialogue_nodes(user_node_id, ai_node_id)
            if parent_id:
                await neo4j_client.link_dialogue_nodes(parent_id, user_node_id)

            # =====================================================
            # 4. 构建思维导图节点
            # 关键：必须创建 _root 节点，前端才能画出图来！
            # =====================================================
            if root_label:
                mindmap_root_id = f"{conversation_id}_root"
                
                # 创建思维导图的根节点 (type='root')
                await neo4j_client.save_dialogue_node(
                    node_id=mindmap_root_id,
                    user_id=user_id,
                    role="assistant",
                    content=root_label, 
                    title=root_label,
                    type="root",
                    mastery_score=node_mastery_score
                )
                
                # 把这个根节点挂在 AI 的回答下面
                await neo4j_client.link_dialogue_nodes(ai_node_id, mindmap_root_id)

                # 创建并连接所有子概念 (type='keyword')
                for child_concept in children:
                    # 简单处理：使用 uuid 确保 ID 唯一，防止同名概念冲突导致图结构混乱
                    child_id = str(uuid.uuid4())
                    
                    await neo4j_client.save_dialogue_node(
                        node_id=child_id,
                        user_id=user_id,
                        role="assistant",
                        content=child_concept,
                        title=child_concept,
                        type="keyword",
                        mastery_score=node_mastery_score
                    )
                    
                    # 连线：Root -> Child
                    await neo4j_client.link_dialogue_nodes(mindmap_root_id, child_id)

                logger.info(
                    "[stream] 思维导图节点构建完成: Root=%s, Children=%s",
                    root_label,
                    len(children),
                )
            else:
                logger.warning("[stream] 未提取到 Root 概念，跳过思维导图节点创建")

        except Exception as e:
            logger.warning(
                "[stream] 递归追问后处理失败（已降级处理）: %s",
                str(e),
                exc_info=True,
            )

    async def process_recursive_query(
        self,
        user_id: str,
        parent_id: str,
        fragment_id: str,
        query: str,
        selected_text: str | None = None,
    ) -> AgentResponse:
        """
        处理递归追问（非流式）
        """
        logger.info(f"开始处理递归追问: fragment_id={fragment_id}, query={query[:50]}...")
        
        # 获取父对话上下文
        parent_context = ""
        try:
            logger.info(f"获取父对话上下文: parent_id={parent_id}")
            # 尝试从Neo4j获取父对话内容
            parent_node = await neo4j_client.get_dialogue_node(parent_id)
            if parent_node and parent_node.get('content'):
                parent_context = parent_node['content']
                logger.info(f"成功获取父对话上下文，长度: {len(parent_context)}")
            else:
                logger.warning("无法获取父对话上下文，使用默认提示词")
        except Exception as e:
            logger.warning(f"获取父对话上下文失败: {str(e)}")

        # 使用递归提示词，结合父对话上下文和选中的文本
        parent_snippet = (parent_context[:500] + "...") if parent_context else ""
        if parent_context and selected_text:
            prompt = RECURSIVE_ANSWER_WITH_SELECTION.format(
                recursive_prompt=RECURSIVE_PROMPT,
                parent_context=parent_snippet,
                selected_text=selected_text,
                query=query,
            )
        elif parent_context:
            prompt = RECURSIVE_ANSWER_WITH_CONTEXT.format(
                recursive_prompt=RECURSIVE_PROMPT,
                parent_context=parent_snippet,
                query=query,
            )
        else:
            prompt = RECURSIVE_ANSWER_QUERY_ONLY.format(
                recursive_prompt=RECURSIVE_PROMPT,
                query=query,
            )

        logger.info("调用LLM生成回答...")
        response_text = await self.llm.acomplete(prompt)
        answer = response_text.text if hasattr(response_text, "text") else str(
            response_text
        )
        logger.info("LLM回答生成完成")

        # 生成对话ID
        conversation_id = str(uuid.uuid4())
        logger.info(f"生成对话ID: {conversation_id}")

        # 保存到Neo4j（降级模式）
        try:
            # 创建用户节点
            user_node_id = f"{conversation_id}_user"
            await neo4j_client.save_dialogue_node(
                node_id=user_node_id,
                user_id=user_id,
                role="user",
                content=query,
                intent="recursive",
            )

            # 创建AI节点
            ai_node_id = conversation_id
            await neo4j_client.save_dialogue_node(
                node_id=ai_node_id,
                user_id=user_id,
                role="assistant",
                content=answer,
                intent="recursive",
            )

            # 创建用户到AI的关系
            await neo4j_client.link_dialogue_nodes(
                parent_node_id=user_node_id,
                child_node_id=ai_node_id,
            )

            # 创建父节点到用户节点的关系
            if parent_id:
                await neo4j_client.link_dialogue_nodes(
                    parent_node_id=parent_id,
                    child_node_id=user_node_id,
                )
            logger.info("递归追问对话保存到Neo4j成功")
        except Exception as e:
            logger.warning(
                "保存递归追问对话到Neo4j失败（已降级处理）: %s",
                str(e),
                exc_info=True,
            )

        # 提取知识三元组
        logger.info("提取知识三元组...")
        try:
            knowledge_triples = knowledge_extractor.extract_triples(answer)
            logger.info(f"成功提取 {len(knowledge_triples)} 个知识三元组")
        except Exception as e:
            logger.warning(f"知识三元组提取失败: {str(e)}", exc_info=True)
            knowledge_triples = []

        return AgentResponse(
            answer=answer,
            fragments=[],
            knowledge_triples=knowledge_triples,
            conversation_id=conversation_id,
            parent_id=parent_id,
        )
