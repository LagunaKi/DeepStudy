import asyncio
from types import SimpleNamespace

import pytest
from google.genai import errors, types

from backend.agent import llm_client


class FakeModels:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text="Gemini response")

    async def generate_content_stream(self, **kwargs):
        self.calls.append(kwargs)

        async def chunks():
            for text in ("Gemini ", "stream"):
                yield SimpleNamespace(text=text)

        return chunks()


class FakeAsyncClient:
    def __init__(self) -> None:
        self.models = FakeModels()
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class FakeClient:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.aio = FakeAsyncClient()


def test_missing_gemini_api_key_is_rejected() -> None:
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        llm_client.GeminiLLMClient(
            model_name="gemini-3-flash-preview",
            api_key="",
        )


def test_complete_and_stream_use_gemini(monkeypatch) -> None:
    fake_root = FakeClient(api_key="test-key")
    monkeypatch.setattr(llm_client.genai, "Client", lambda api_key: fake_root)

    async def run_client() -> tuple[llm_client.LLMResponse, list[str]]:
        client = llm_client.GeminiLLMClient(
            model_name="gemini-3-flash-preview",
            api_key="test-key",
            thinking_level="medium",
        )

        response = await client.acomplete("explain RAG")
        chunks = [chunk async for chunk in client.astream("explain agents")]
        await client.close()
        return response, chunks

    response, chunks = asyncio.run(run_client())

    assert response.text == "Gemini response"
    assert chunks == ["Gemini ", "stream"]
    assert fake_root.aio.models.calls[0]["model"] == "gemini-3-flash-preview"
    assert fake_root.aio.models.calls[0]["contents"] == "explain RAG"
    assert fake_root.aio.closed is True


def test_function_calling_is_manual_and_uses_declared_tools(monkeypatch) -> None:
    fake_root = FakeClient(api_key="test-key")
    model_content = types.Content(
        role="model",
        parts=[
            types.Part(
                function_call=types.FunctionCall(
                    id="call-1",
                    name="calculate_expression",
                    args={"expression": "2 + 2"},
                )
            )
        ],
    )

    async def generate_content(**kwargs):
        fake_root.aio.models.calls.append(kwargs)
        return SimpleNamespace(
            text="",
            function_calls=[model_content.parts[0].function_call],
            candidates=[SimpleNamespace(content=model_content)],
        )

    fake_root.aio.models.generate_content = generate_content
    monkeypatch.setattr(llm_client.genai, "Client", lambda api_key: fake_root)

    async def scenario() -> llm_client.GeminiFunctionResponse:
        client = llm_client.GeminiLLMClient(
            model_name="function-test-model",
            api_key="test-key",
        )
        return await client.acomplete_with_tools(
            contents=[types.Content(role="user", parts=[types.Part(text="2+2")])],
            system_instruction="Use a calculator when useful.",
            tool_declarations=[
                types.FunctionDeclaration(
                    name="calculate_expression",
                    description="calculate",
                    parameters_json_schema={
                        "type": "object",
                        "properties": {"expression": {"type": "string"}},
                        "required": ["expression"],
                    },
                )
            ],
        )

    response = asyncio.run(scenario())
    config = fake_root.aio.models.calls[0]["config"]

    assert response.function_calls[0].name == "calculate_expression"
    assert response.function_calls[0].arguments == {"expression": "2 + 2"}
    assert config.automatic_function_calling.disable is True
    assert config.tools[0].function_declarations[0].name == "calculate_expression"


def test_streaming_function_calling_yields_text_chunks(monkeypatch) -> None:
    fake_root = FakeClient(api_key="test-key")

    async def generate_content_stream(**kwargs):
        fake_root.aio.models.calls.append(kwargs)

        async def chunks():
            for text in ("逐段", "回答"):
                content = types.Content(role="model", parts=[types.Part(text=text)])
                yield SimpleNamespace(
                    text=text,
                    function_calls=[],
                    candidates=[SimpleNamespace(content=content)],
                )

        return chunks()

    fake_root.aio.models.generate_content_stream = generate_content_stream
    monkeypatch.setattr(llm_client.genai, "Client", lambda api_key: fake_root)

    async def scenario() -> list[llm_client.GeminiFunctionChunk]:
        client = llm_client.GeminiLLMClient(
            model_name="function-stream-test-model",
            api_key="test-key",
        )
        return [
            chunk
            async for chunk in client.astream_with_tools(
                contents=[types.Content(role="user", parts=[types.Part(text="解释 Agent")])],
                system_instruction="Teach clearly.",
                tool_declarations=[
                    types.FunctionDeclaration(
                        name="calculate_expression",
                        description="calculate",
                        parameters_json_schema={"type": "object", "properties": {}},
                    )
                ],
            )
        ]

    chunks = asyncio.run(scenario())

    assert [chunk.text for chunk in chunks] == ["逐段", "回答"]
    config = fake_root.aio.models.calls[0]["config"]
    assert config.automatic_function_calling.disable
    assert config.tool_config.function_calling_config.stream_function_call_arguments is None


def test_rate_limit_error_is_sanitized_and_exposes_retry_delay(monkeypatch) -> None:
    class RateLimitedModels:
        async def generate_content_stream(self, **_kwargs):
            raise errors.ClientError(
                429,
                {
                    "error": {
                        "code": 429,
                        "status": "RESOURCE_EXHAUSTED",
                        "message": "raw provider quota details",
                        "details": [
                            {
                                "@type": "type.googleapis.com/google.rpc.RetryInfo",
                                "retryDelay": "31.8s",
                            }
                        ],
                    }
                },
            )

    fake_root = FakeClient(api_key="test-key")
    fake_root.aio.models = RateLimitedModels()
    monkeypatch.setattr(llm_client.genai, "Client", lambda api_key: fake_root)

    async def consume_stream() -> None:
        client = llm_client.GeminiLLMClient(
            model_name="rate-limit-test-model",
            api_key="test-key",
        )
        async for _chunk in client.astream("hello"):
            pass

    with pytest.raises(llm_client.LLMRateLimitError) as captured:
        asyncio.run(consume_stream())

    assert captured.value.retry_after == 32
    assert str(captured.value) == "Gemini 免费额度暂时繁忙，请在 32 秒后重试。"


def test_daily_quota_is_not_reported_as_short_cooldown() -> None:
    provider_error = errors.ClientError(
        429,
        {
            "message": (
                '{"error":{"code":429,"status":"RESOURCE_EXHAUSTED",'
                '"details":[{"quotaId":'
                '"GenerateRequestsPerDayPerProjectPerModel-FreeTier",'
                '"quotaValue":"20"},{"retryDelay":"31s"}]}}'
            ),
            "status": "Too Many Requests",
        },
    )

    rate_limit_error = llm_client._rate_limit_error(provider_error)

    assert rate_limit_error is not None
    assert rate_limit_error.code == "quota_exhausted"
    assert rate_limit_error.daily_quota is True
    assert rate_limit_error.retry_after == 0
    assert "20 次" in str(rate_limit_error)
