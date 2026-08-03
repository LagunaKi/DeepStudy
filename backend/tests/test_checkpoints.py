import asyncio

from backend.agent.checkpoints import checkpoint_saver, checkpoint_status
from backend.config import settings
from backend.tests.test_agent_graph import (
    AgentGraphWithoutExternalMemory,
    FakeProvider,
    _state,
)


class FailingProvider:
    async def generate_stream(self, **_kwargs):
        if False:
            yield None
        raise RuntimeError("simulated disconnect")


def test_langgraph_checkpoint_is_persisted_across_connections(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        settings,
        "LANGGRAPH_CHECKPOINT_DB_PATH",
        str(tmp_path / "checkpoints.db"),
    )

    async def scenario() -> None:
        async with checkpoint_saver() as saver:
            runtime = AgentGraphWithoutExternalMemory(
                FakeProvider(use_tool=False), checkpointer=saver
            )
            events = [event async for event in runtime.stream(_state("什么是 Agent？"))]
            assert any(event.get("node") == "verifier" for event in events)
        status = await checkpoint_status("session-1")
        assert status["available"] is True
        assert status["conversation_id"] == "conversation-1"
        assert status["has_answer"] is True

    asyncio.run(scenario())


def test_interrupted_graph_resumes_from_last_persisted_node(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        settings,
        "LANGGRAPH_CHECKPOINT_DB_PATH",
        str(tmp_path / "resume.db"),
    )

    async def scenario() -> None:
        async with checkpoint_saver() as saver:
            interrupted = AgentGraphWithoutExternalMemory(
                FailingProvider(), checkpointer=saver
            )
            try:
                async for _event in interrupted.stream(_state("什么是 RAG？")):
                    pass
            except RuntimeError as exc:
                assert "simulated disconnect" in str(exc)
            else:
                raise AssertionError("graph should have been interrupted")

        # 模拟进程/连接重建：新 graph 只传 thread_id，即可从失败节点重试。
        async with checkpoint_saver() as saver:
            resumed = AgentGraphWithoutExternalMemory(
                FakeProvider(use_tool=False), checkpointer=saver
            )
            events = [event async for event in resumed.resume("session-1")]
            assert any(event.get("type") == "delta" for event in events)
            assert any(event.get("node") == "memory_writer" for event in events)

    asyncio.run(scenario())
