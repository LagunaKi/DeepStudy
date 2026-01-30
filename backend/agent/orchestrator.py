"""
Agent 编排器
使用自定义 LLM 客户端编排对话流程
"""
import uuid
import logging
import json
from typing import AsyncGenerator, Optional

from backend.agent.llm_client import ModelScopeLLMClient
from backend.agent.intent_router import IntentRouter, IntentType
from backend.agent.strategies import DerivationStrategy, CodeStrategy, ConceptStrategy
<<<<<<< HEAD
from backend.agent.extractors import knowledge_extractor
=======
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
from backend.agent.prompts.system_prompts import RECURSIVE_PROMPT
from backend.api.schemas.response import AgentResponse
from backend.data.neo4j_client import neo4j_client
from backend.config import settings

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

        logger.info(f"初始化主模型: {settings.MODEL_NAME}")
        # 使用 OpenAI 兼容 API
        self.llm = ModelScopeLLMClient(
            model_name=settings.MODEL_NAME,
            api_key=settings.MODELSCOPE_API_KEY,
            api_base=settings.MODELSCOPE_API_BASE,
        )
        logger.info("主模型初始化成功")

        logger.info(f"初始化 Coder 模型: {settings.CODER_MODEL_NAME}")
        self.coder_llm = ModelScopeLLMClient(
            model_name=settings.CODER_MODEL_NAME,
            api_key=settings.MODELSCOPE_API_KEY,
            api_base=settings.MODELSCOPE_API_BASE,
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
        parent_id: Optional[str] = None,
        session_id: Optional[str] = None,
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

<<<<<<< HEAD
        # 提取知识三元组
        logger.info("提取知识三元组...")
        knowledge_triples = knowledge_extractor.extract_triples(response.answer)
        response.knowledge_triples = knowledge_triples
        logger.info(f"成功提取 {len(knowledge_triples)} 个知识三元组")

=======
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
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
        parent_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
<<<<<<< HEAD
        处理用户查询（流式输出）

        返回一个异步生成器，按行输出 JSON 字符串：
        - 第一行: {\"type\":\"meta\",\"conversation_id\":...}
        - 后续多行: {\"type\":\"delta\",\"text\":...}
        - 结束行: {\"type\":\"end\"}
        """
        logger.info(f"[stream] 开始处理查询: query={query[:50]}...")
        logger.info("[stream] 识别意图...")
=======
        处理用户查询（流式输出 + 知识提炼）
        """
        logger.info(f"[stream] 开始处理查询: query={query[:50]}...")
        
        # 1. 意图识别
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
        intent = await self.intent_router.route(query)
        logger.info(f"[stream] 识别结果: {intent.value}")

        strategy = self.strategies[intent]
        context = {
            "user_id": user_id,
            "parent_id": parent_id,
        }

<<<<<<< HEAD
        # 生成对话 ID，并提前下发给前端
        conversation_id = str(uuid.uuid4())
        logger.info(f"[stream] 生成对话 ID: {conversation_id}")

        # 缓存完整回答，用于流结束后写入 Neo4j
        answer_parts: list[str] = []

        # 首包：meta 信息
        meta_payload = {"type": "meta", "conversation_id": conversation_id}
        yield json.dumps(meta_payload, ensure_ascii=False) + "\n"

        try:
            # 调用策略的流式接口
            async for delta in strategy.process_stream(query, context):  # type: ignore[attr-defined]
                if not delta:
                    continue
                answer_parts.append(delta)
                payload = {"type": "delta", "text": delta}
                yield json.dumps(payload, ensure_ascii=False) + "\n"
        except Exception as e:
            logger.error("[stream] LLM 流式生成失败: %s", str(e), exc_info=True)
            error_payload = {"type": "error", "message": str(e)}
            yield json.dumps(error_payload, ensure_ascii=False) + "\n"
        finally:
            # 结束标记
            yield json.dumps({"type": "end"}, ensure_ascii=False) + "\n"

            # 在后台保存到 Neo4j（降级模式）
            full_answer = "".join(answer_parts)
            logger.info("[stream] 开始保存流式回答到 Neo4j...")
            try:
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
                    logger.info("[stream] 创建父节点关系: parent_id=%s", parent_id)
                    await neo4j_client.link_dialogue_nodes(
                        parent_node_id=parent_id,
                        child_node_id=user_node_id,
                    )
                # 提取知识三元组
                logger.info("[stream] 提取知识三元组...")
                knowledge_triples = knowledge_extractor.extract_triples(full_answer)
                logger.info(f"[stream] 成功提取 {len(knowledge_triples)} 个知识三元组")
                
                logger.info("[stream] Neo4j 保存成功")
            except Exception as e:
                logger.warning(
                    "[stream] 保存流式对话到 Neo4j 失败（已降级处理）: %s",
                    str(e),
                    exc_info=True,
                )

=======
        # 生成对话 ID
        conversation_id = str(uuid.uuid4())
        
        answer_parts = [] 
       
        # 发送 Meta 信息
        yield json.dumps({"type": "meta", "conversation_id": conversation_id}, ensure_ascii=False) + "\n"

        try:
            # 2. 流式生成回答
            async for delta in strategy.process_stream(query, context):
                if not delta:
                    continue
                
                # 收集回答片段
                answer_parts.append(delta)
                
                # 发送给前端
                payload = {"type": "delta", "text": delta}
                yield json.dumps(payload, ensure_ascii=False) + "\n"
                
        except Exception as e:
            logger.error("[stream] LLM 流式生成失败: %s", str(e), exc_info=True)
            yield json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False) + "\n"
            return # 出错就直接结束，不进行后续提炼
            
        finally:
            # 发送结束标记
            yield json.dumps({"type": "end"}, ensure_ascii=False) + "\n"

        # ==========================================
        # 3. 后处理：AI 知识提炼 (Concept Extraction)
        # ==========================================
        full_answer = "".join(answer_parts)
        
        if not full_answer:
            return

        logger.info("[stream] 回答结束，开始进行知识提炼...")

        try:
            # A. 调用 LLM 总结结构
            extraction_prompt = f"""
            基于以下问答，提炼出一个核心概念节点和3-5个关键子概念节点。
            
            问题: {query}
            回答: {full_answer}
            
            请严格只返回 JSON 格式，不要包含 Markdown 标记。格式如下：
            {{
                "root": "核心概念(简短名词)",
                "children": ["子概念1", "子概念2", "子概念3"]
            }}
            """
            
            summary_res = await self.llm.acomplete(extraction_prompt)
            summary_text = summary_res.text if hasattr(summary_res, 'text') else str(summary_res)
            
            # 清理 JSON 字符串
            summary_text = summary_text.replace("```json", "").replace("```", "").strip()
            
            # 解析 JSON
            try:
                structure = json.loads(summary_text)
                root_label = structure.get("root", "核心概念")
                children = structure.get("children", [])
            except json.JSONDecodeError:
                logger.warning("知识提炼 JSON 解析失败，使用默认值")
                root_label = query[:10]
                children = []

            logger.info(f"提炼成功: Root={root_label}, Children={children}")

            # B. 存 Root 节点 (问题 + 回答 + Root Title)
            user_node_id = f"{conversation_id}_root"
            
            # 存 Root (Title = 核心概念, Type = root)
            await neo4j_client.save_dialogue_node(
                node_id=user_node_id,
                user_id=user_id,
                role="user",
                content=query, # 节点内容还是存完整问题
                title=root_label, #  标题存 AI 提炼的核心词
                type="root"       #  类型标记为 root
            )

            # C. 存 AI 回答节点 (详情)
            ai_node_id = conversation_id
            await neo4j_client.save_dialogue_node(
                node_id=ai_node_id,
                user_id=user_id,
                role="assistant",
                content=full_answer,
                title="详细解释",
                type="explanation"
            )
            # 连线: Root -> Explanation
            await neo4j_client.link_dialogue_nodes(user_node_id, ai_node_id)
            
            # D. 存关键子概念 (Keywords)
            for child_concept in children:
                child_id = str(uuid.uuid4())
                
                # 使用 query 方法直接创建子节点和连线
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
                        "name": child_concept
                    }
                )

            logger.info("[stream] 知识图谱构建完成")

        except Exception as e:
            logger.error(f"知识提炼失败: {e}", exc_info=True)
            # 降级：仅保存基本的问答对
            try:
                await neo4j_client.save_dialogue_node(f"{conversation_id}_user", user_id, "user", query, title="问题")
                await neo4j_client.save_dialogue_node(conversation_id, user_id, "assistant", full_answer, title="回答")
                await neo4j_client.link_dialogue_nodes(f"{conversation_id}_user", conversation_id)
            except Exception as e2:
                 logger.error(f"降级保存也失败了: {e2}")

>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
    async def process_recursive_query(
        self,
        user_id: str,
        parent_id: str,
        fragment_id: str,
        query: str,
<<<<<<< HEAD
        selected_text: Optional[str] = None,
=======
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
    ) -> AgentResponse:
        """
        处理递归追问（非流式）
        """
<<<<<<< HEAD
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
        if parent_context and selected_text:
            prompt = f"{RECURSIVE_PROMPT}\n\n之前的回答: {parent_context[:500]}...\n\n用户选中的文本: {selected_text}\n\n用户追问: {query}\n\n请针对性地回答："
        elif parent_context:
            prompt = f"{RECURSIVE_PROMPT}\n\n之前的回答: {parent_context[:500]}...\n\n用户追问: {query}\n\n请针对性地回答："
        else:
            prompt = f"{RECURSIVE_PROMPT}\n\n用户追问: {query}\n\n请针对性地回答："

        logger.info("调用LLM生成回答...")
=======
        # TODO: 获取父对话上下文
        # TODO: 获取片段内容

        # 使用递归提示词
        prompt = f"{RECURSIVE_PROMPT}\n\n用户追问: {query}\n\n请针对性地回答："

>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
        response_text = await self.llm.acomplete(prompt)
        answer = response_text.text if hasattr(response_text, "text") else str(
            response_text
        )
<<<<<<< HEAD
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
        knowledge_triples = knowledge_extractor.extract_triples(answer)
        logger.info(f"成功提取 {len(knowledge_triples)} 个知识三元组")
=======
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45

        return AgentResponse(
            answer=answer,
            fragments=[],
<<<<<<< HEAD
            knowledge_triples=knowledge_triples,
=======
            knowledge_triples=[],
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
            conversation_id=str(uuid.uuid4()),
            parent_id=parent_id,
        )

