import asyncio
from types import SimpleNamespace

import pytest

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
