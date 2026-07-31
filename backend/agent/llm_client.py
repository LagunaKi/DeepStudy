"""Gemini LLM 客户端。

使用 Google Gen AI SDK 访问 Gemini Developer API，并保持策略层依赖的
``acomplete`` / ``astream`` 接口稳定。
"""

import logging
from collections.abc import AsyncGenerator

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


class GeminiLLMClient:
    """使用 Google Gen AI SDK 的异步文本生成客户端。"""

    def __init__(
        self,
        model_name: str,
        api_key: str,
        thinking_level: str = "medium",
        max_output_tokens: int = 4000,
    ) -> None:
        if not api_key:
            raise RuntimeError(
                "未配置 GEMINI_API_KEY。请复制 .env.example 为 backend/.env 后填写密钥。"
            )

        self.model_name = model_name
        self.thinking_level = thinking_level
        self.max_output_tokens = max_output_tokens
        self.client = genai.Client(api_key=api_key).aio
        self.generation_config = types.GenerateContentConfig(
            max_output_tokens=max_output_tokens,
            thinking_config=types.ThinkingConfig(
                thinking_level=types.ThinkingLevel(thinking_level.upper()),
                include_thoughts=False,
            ),
        )
        logger.info(
            "GeminiLLMClient 初始化: model=%s, thinking_level=%s",
            model_name,
            thinking_level,
        )

    async def acomplete(self, prompt: str) -> "LLMResponse":
        """生成一次非流式文本回复。"""
        try:
            logger.info("调用 Gemini API: model=%s", self.model_name)
            response = await self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=self.generation_config,
            )
            content = response.text or ""
            logger.info("API 调用成功，返回长度: %d", len(content))
            return LLMResponse(text=content)
        except Exception as exc:
            logger.error("LLM API 调用失败: %s", exc, exc_info=True)
            raise RuntimeError(f"LLM API 调用失败: {exc}") from exc

    async def astream(self, prompt: str) -> AsyncGenerator[str, None]:
        """流式生成文本。"""
        logger.info("调用 Gemini API（stream）: model=%s", self.model_name)
        try:
            stream = await self.client.models.generate_content_stream(
                model=self.model_name,
                contents=prompt,
                config=self.generation_config,
            )
            async for chunk in stream:
                text = chunk.text
                if text:
                    yield text
        except Exception as exc:
            logger.error("LLM 流式 API 调用失败: %s", exc, exc_info=True)
            raise RuntimeError(f"LLM API 调用失败: {exc}") from exc

    async def close(self) -> None:
        """关闭底层 HTTP 客户端。"""
        await self.client.aclose()


class LLMResponse:
    """兼容现有策略层的轻量文本响应。"""

    def __init__(self, text: str):
        self.text = text

    def __str__(self) -> str:
        return self.text
