"""
代码型策略
"""
from backend.agent.strategies.base_strategy import BaseStrategy
from backend.agent.prompts.system_prompts import CODE_PROMPT
from backend.api.schemas.response import AgentResponse


class CodeStrategy(BaseStrategy):
    """代码型问题处理策略"""
    
    def __init__(self, llm):
        """
        初始化策略
        
        Args:
            llm: 大语言模型实例（应使用 Coder 模型）
        """
        self.llm = llm
        self.system_prompt = CODE_PROMPT
    
    async def process(
        self,
        query: str,
        context: dict = None
    ) -> AgentResponse:
        """
        处理代码型问题
        
        Args:
            query: 用户查询
            context: 上下文信息
            
        Returns:
            Agent 响应
        """
        # TODO: 实现代码型问题的处理逻辑
        # 这里先返回占位响应
        prompt = f"{self.system_prompt}\n\n问题: {query}\n\n请提供代码实现："
        
        response_text = await self.llm.acomplete(prompt)
        answer = response_text.text if hasattr(response_text, 'text') else str(response_text)
        
        return AgentResponse(
            answer=answer,
            fragments=[],
            knowledge_triples=[],
            conversation_id="",  # 由 orchestrator 生成
            parent_id=context.get("parent_id") if context else None
        )

    async def process_stream(
        self,
        query: str,
        context: dict = None
    ):
        """
        代码型问题流式处理
        
        返回一个异步生成器，逐步产生回答文本。
        """
        # 构建提示词，如果有父对话上下文则注入
        if context and context.get("parent_context"):
            parent_context = context["parent_context"]
            prompt = f"""{self.system_prompt}

之前的对话：
{parent_context[:500]}...

当前问题: {query}

请基于之前的对话上下文，提供代码实现："""
        else:
            prompt = f"{self.system_prompt}\n\n问题: {query}\n\n请提供代码实现："
        
        async for delta in self.llm.astream(prompt):
            yield delta
