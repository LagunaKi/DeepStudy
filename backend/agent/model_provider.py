"""可替换的 Agent 模型 Provider 接口。"""

from collections.abc import AsyncGenerator
from typing import Protocol

from google.genai import types

from backend.agent.llm_client import (
    GeminiFunctionChunk,
    GeminiFunctionResponse,
    GeminiLLMClient,
)


class AgentModelProvider(Protocol):
    """LangGraph 仅依赖这个协议，不直接依赖某个模型 SDK。"""

    async def generate(
        self,
        *,
        contents: list[types.Content],
        system_instruction: str,
        tool_declarations: list[types.FunctionDeclaration],
        allow_tools: bool = True,
    ) -> GeminiFunctionResponse: ...

    def generate_stream(
        self,
        *,
        contents: list[types.Content],
        system_instruction: str,
        tool_declarations: list[types.FunctionDeclaration],
        allow_tools: bool = True,
    ) -> AsyncGenerator[GeminiFunctionChunk, None]: ...


class GeminiModelProvider:
    """Google Gen AI SDK Provider。"""

    def __init__(self, client: GeminiLLMClient) -> None:
        self.client = client

    async def generate(
        self,
        *,
        contents: list[types.Content],
        system_instruction: str,
        tool_declarations: list[types.FunctionDeclaration],
        allow_tools: bool = True,
    ) -> GeminiFunctionResponse:
        return await self.client.acomplete_with_tools(
            contents=contents,
            system_instruction=system_instruction,
            tool_declarations=tool_declarations,
            allow_tools=allow_tools,
        )

    async def generate_stream(
        self,
        *,
        contents: list[types.Content],
        system_instruction: str,
        tool_declarations: list[types.FunctionDeclaration],
        allow_tools: bool = True,
    ) -> AsyncGenerator[GeminiFunctionChunk, None]:
        async for chunk in self.client.astream_with_tools(
            contents=contents,
            system_instruction=system_instruction,
            tool_declarations=tool_declarations,
            allow_tools=allow_tools,
        ):
            yield chunk
