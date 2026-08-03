import asyncio

from backend.agent.skills import skill_catalog
from backend.mcp_server import mcp


def test_skill_catalog_selects_progressively_disclosed_skill() -> None:
    metadata = skill_catalog.select("请推导贝叶斯公式", "derivation")
    assert metadata is not None
    assert metadata.name == "derive-formula"
    instruction = skill_catalog.load_instructions(metadata)
    assert "声明符号、假设和目标" in instruction

    practice = skill_catalog.select("围绕 RAG 出三道练习题", "concept")
    assert practice is not None
    assert practice.name == "generate-practice"


def test_mcp_server_exposes_tools_resources_and_prompts() -> None:
    async def scenario() -> tuple[set[str], set[str], set[str]]:
        tools = {item.name for item in await mcp.list_tools()}
        templates = {item.name for item in await mcp.list_resource_templates()}
        prompts = {item.name for item in await mcp.list_prompts()}
        return tools, templates, prompts

    tools, templates, prompts = asyncio.run(scenario())
    assert {"search_course", "query_concept_graph", "create_quiz"} <= tools
    assert {"course-outline", "concept-resource"} <= templates
    assert {"guided_explanation", "review_session"} <= prompts
