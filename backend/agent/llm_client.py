"""Gemini LLM 客户端。

使用 Google Gen AI SDK 访问 Gemini Developer API，并保持策略层依赖的
``acomplete`` / ``astream`` 接口稳定。
"""

import asyncio
import logging
import math
import re
import time
from collections.abc import AsyncGenerator
from typing import Any

from google import genai
from google.genai import errors, types

logger = logging.getLogger(__name__)


class LLMRateLimitError(RuntimeError):
    """可安全返回给前端的 Gemini 限流异常。"""

    def __init__(
        self,
        retry_after: int = 0,
        *,
        daily_quota: bool = False,
        quota_limit: int | None = None,
    ) -> None:
        self.daily_quota = daily_quota
        self.retry_after = 0 if daily_quota else max(1, retry_after)
        self.code = "quota_exhausted" if daily_quota else "rate_limit"
        if daily_quota:
            limit_text = f"（{quota_limit} 次）" if quota_limit else ""
            message = (
                f"Gemini 3 Flash 今日免费请求额度{limit_text}已用完，"
                "请等待 Google 配额重置后再试。"
            )
        else:
            message = f"Gemini 免费额度暂时繁忙，请在 {self.retry_after} 秒后重试。"
        super().__init__(message)


class _GeminiRequestGate:
    """进程内共享的请求节流与 429 冷却器。"""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._last_started_at: dict[str, float] = {}
        self._cooldown_until: dict[str, float] = {}

    async def acquire(self, model_name: str, min_interval: float) -> None:
        now = time.monotonic()
        cooldown_remaining = self._cooldown_until.get(model_name, 0.0) - now
        if cooldown_remaining > 0:
            raise LLMRateLimitError(math.ceil(cooldown_remaining))

        async with self._lock:
            now = time.monotonic()
            cooldown_remaining = self._cooldown_until.get(model_name, 0.0) - now
            if cooldown_remaining > 0:
                raise LLMRateLimitError(math.ceil(cooldown_remaining))

            wait_seconds = max(
                0.0,
                self._last_started_at.get(model_name, 0.0) + min_interval - now,
            )
            if wait_seconds:
                logger.info("Gemini 免费层节流，等待 %.1f 秒", wait_seconds)
                await asyncio.sleep(wait_seconds)
            self._last_started_at[model_name] = time.monotonic()

    def register_rate_limit(self, model_name: str, retry_after: int) -> None:
        self._cooldown_until[model_name] = max(
            self._cooldown_until.get(model_name, 0.0),
            time.monotonic() + retry_after,
        )


_REQUEST_GATE = _GeminiRequestGate()


def _find_retry_delay(value: Any) -> float | None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "retryDelay" and isinstance(child, str):
                match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)s", child.strip())
                if match:
                    return float(match.group(1))
            nested = _find_retry_delay(child)
            if nested is not None:
                return nested
    elif isinstance(value, list):
        for child in value:
            nested = _find_retry_delay(child)
            if nested is not None:
                return nested
    return None


def _find_daily_quota(value: Any) -> int | None:
    if isinstance(value, dict):
        quota_id = value.get("quotaId")
        if isinstance(quota_id, str) and "PerDay" in quota_id:
            quota_value = value.get("quotaValue")
            if isinstance(quota_value, str) and quota_value.isdigit():
                return int(quota_value)
            return 0
        for child in value.values():
            result = _find_daily_quota(child)
            if result is not None:
                return result
    elif isinstance(value, list):
        for child in value:
            result = _find_daily_quota(child)
            if result is not None:
                return result
    return None


def _rate_limit_error(exc: Exception) -> LLMRateLimitError | None:
    code = getattr(exc, "code", None)
    status = getattr(exc, "status", None)
    if not (
        isinstance(exc, errors.ClientError) and code == 429
        or code == 429
        or status == "RESOURCE_EXHAUSTED"
    ):
        return None

    details = getattr(exc, "details", None)
    raw_error = str(exc)
    daily_quota = _find_daily_quota(details)
    if daily_quota is None and re.search(r"quotaId[^\n]*PerDay", raw_error):
        limit_match = re.search(r"quotaValue[^0-9]*([0-9]+)", raw_error)
        daily_quota = int(limit_match.group(1)) if limit_match else 0
    if daily_quota is not None:
        return LLMRateLimitError(
            daily_quota=True,
            quota_limit=daily_quota or None,
        )

    retry_delay = _find_retry_delay(details)
    if retry_delay is None:
        match = re.search(r"retryDelay[^0-9]*([0-9]+(?:\.[0-9]+)?)s", raw_error)
        retry_delay = float(match.group(1)) if match else 60.0
    return LLMRateLimitError(math.ceil(retry_delay))


class GeminiLLMClient:
    """使用 Google Gen AI SDK 的异步文本生成客户端。"""

    def __init__(
        self,
        model_name: str,
        api_key: str,
        thinking_level: str = "medium",
        max_output_tokens: int = 4000,
        min_request_interval_seconds: float = 0.0,
    ) -> None:
        if not api_key:
            raise RuntimeError(
                "未配置 GEMINI_API_KEY。请复制 .env.example 为 backend/.env 后填写密钥。"
            )

        self.model_name = model_name
        self.thinking_level = thinking_level
        self.max_output_tokens = max_output_tokens
        self.min_request_interval_seconds = max(0.0, min_request_interval_seconds)
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
            await _REQUEST_GATE.acquire(self.model_name, self.min_request_interval_seconds)
            logger.info("调用 Gemini API: model=%s", self.model_name)
            response = await self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=self.generation_config,
            )
            content = response.text or ""
            logger.info("API 调用成功，返回长度: %d", len(content))
            return LLMResponse(text=content)
        except LLMRateLimitError:
            raise
        except Exception as exc:
            logger.error("LLM API 调用失败: %s", exc, exc_info=True)
            rate_limit_error = _rate_limit_error(exc)
            if rate_limit_error:
                if not rate_limit_error.daily_quota:
                    _REQUEST_GATE.register_rate_limit(
                        self.model_name, rate_limit_error.retry_after
                    )
                raise rate_limit_error from exc
            raise RuntimeError(f"LLM API 调用失败: {exc}") from exc

    async def astream(self, prompt: str) -> AsyncGenerator[str, None]:
        """流式生成文本。"""
        logger.info("调用 Gemini API（stream）: model=%s", self.model_name)
        try:
            await _REQUEST_GATE.acquire(self.model_name, self.min_request_interval_seconds)
            stream = await self.client.models.generate_content_stream(
                model=self.model_name,
                contents=prompt,
                config=self.generation_config,
            )
            async for chunk in stream:
                text = chunk.text
                if text:
                    yield text
        except LLMRateLimitError:
            raise
        except Exception as exc:
            logger.error("LLM 流式 API 调用失败: %s", exc, exc_info=True)
            rate_limit_error = _rate_limit_error(exc)
            if rate_limit_error:
                if not rate_limit_error.daily_quota:
                    _REQUEST_GATE.register_rate_limit(
                        self.model_name, rate_limit_error.retry_after
                    )
                raise rate_limit_error from exc
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
