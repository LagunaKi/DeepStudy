"""
概念型策略
"""
from backend.agent.strategies.base_strategy import BaseStrategy
from backend.agent.prompts.system_prompts import CONCEPT_PROMPT
from backend.api.schemas.response import AgentResponse


class ConceptStrategy(BaseStrategy):
    """概念型问题处理策略"""

    def __init__(self, llm):
        """
        初始化策略
        
        Args:
            llm: 大语言模型实例
        """
        self.llm = llm
        self.system_prompt = CONCEPT_PROMPT

    async def process(
        self,
        query: str,
        context: dict | None = None,
    ) -> AgentResponse:
        """
        处理概念型问题（非流式）
        """
        prompt = f"{self.system_prompt}\n\n问题: {query}\n\n请详细解释这个概念："

        response_text = await self.llm.acomplete(prompt)
        answer = response_text.text if hasattr(response_text, "text") else str(
            response_text
        )

        return AgentResponse(
            answer=answer,
            fragments=[],
            knowledge_triples=[],
            conversation_id="",  # 由 orchestrator 生成
            parent_id=context.get("parent_id") if context else None,
        )

    async def process_stream(
        self,
        query: str,
        context: dict | None = None,
    ):
        """
        概念型问题流式处理
        
        返回一个异步生成器，逐步产生回答文本。
        """
        # 构建提示词，如果有父对话上下文则注入
        if context and context.get("parent_context"):
            parent_context = context["parent_context"]
            prompt = f"""{self.system_prompt}

之前的对话：
{parent_context[:500]}...

当前问题: {query}

请基于之前的对话上下文，详细解释这个概念："""
        else:
            prompt = f"{self.system_prompt}\n\n问题: {query}\n\n请详细解释这个概念："
        
        async for delta in self.llm.astream(prompt):  # type: ignore[attr-defined]
            yield delta
