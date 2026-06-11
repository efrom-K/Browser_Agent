import os

import pytest

from agent import config
from agent.browser.perception import capture_state
from agent.core.llm_client import LLMClient
from agent.core.observation import build_observation
from agent.core.prompts import build_system_prompt
from agent.tools.schema import TOOLS

from .conftest import fixture_url

requires_api_key = pytest.mark.skipif(not config.LLM_API_KEY, reason="LLM API key not set")


@requires_api_key
async def test_agent_picks_search_input_for_search_task(controller):
    await controller.goto(fixture_url("simple_form.html"))
    state = await capture_state(controller.page, mark_screenshot=config.VISION_ENABLED)

    task = "Search for 'playwright' using the search box on this page."
    messages = [
        {
            "role": "user",
            "content": build_observation(state, task, include_screenshot=config.VISION_ENABLED),
        }
    ]

    client = LLMClient()
    system_prompt = build_system_prompt(vision=config.VISION_ENABLED)
    response = await client.step(system_prompt, messages, TOOLS)

    assert response.stop_reason == "tool_use"
    tool_uses = [b for b in response.content if b.type == "tool_use"]
    assert len(tool_uses) == 1

    tool = tool_uses[0]
    input_element = next(el for el in state.elements if el.tag == "input")

    # The model should act on the search input, either typing into it
    # directly or clicking it first.
    assert tool.name in ("type_text", "click")
    assert tool.input["element_id"] == input_element.id
    if tool.name == "type_text":
        assert "playwright" in tool.input["text"].lower()
