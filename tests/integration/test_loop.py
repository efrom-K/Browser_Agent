from dataclasses import dataclass, field
from types import SimpleNamespace

from agent.core.loop import AgentLoop

from .conftest import fixture_url


@dataclass
class FakeLLMClient:
    """Returns a pre-scripted sequence of responses, ignoring the prompt."""

    responses: list[list[SimpleNamespace]]
    calls: list[list[dict]] = field(default_factory=list)
    systems: list[str] = field(default_factory=list)

    async def step(self, system, messages, tools, max_tokens=1024):
        self.calls.append(list(messages))
        self.systems.append(system)
        content = self.responses[len(self.calls) - 1]
        return SimpleNamespace(content=content, stop_reason="tool_use")


def _text(text):
    return SimpleNamespace(type="text", text=text)


def _tool_use(tool_id, name, tool_input):
    return SimpleNamespace(type="tool_use", id=tool_id, name=name, input=tool_input)


async def test_loop_clicks_then_finishes(controller):
    await controller.goto(fixture_url("buttons.html"))

    client = FakeLLMClient(
        responses=[
            [_text("I'll click the counter button."), _tool_use("t1", "click", {"element_id": 0})],
            [_tool_use("t2", "finish_task", {"summary": "Clicked the counter once.", "success": True})],
        ]
    )

    loop = AgentLoop(controller.page, client=client, max_steps=5, vision=True)
    events = []
    result = await loop.run("Click the counter button once.", on_step=events.append)

    assert result.success is True
    assert result.summary == "Clicked the counter once."
    assert result.steps == 2

    assert [e.tool_name for e in events] == ["click", "finish_task"]
    assert events[0].assistant_text == "I'll click the counter button."

    counter_text = await controller.page.text_content("#counter")
    assert counter_text == "Count: 1"

    # Second LLM call should include the tool_result for the click, with a
    # fresh screenshot/observation attached.
    second_call_messages = client.calls[1]
    tool_result_message = second_call_messages[-1]
    assert tool_result_message["role"] == "user"
    tool_result = tool_result_message["content"][0]
    assert tool_result["type"] == "tool_result"
    assert tool_result["tool_use_id"] == "t1"
    assert tool_result["content"][0]["type"] == "text"
    assert tool_result["content"][1]["type"] == "text"
    assert tool_result["content"][2]["type"] == "image"


async def test_loop_text_only_omits_screenshot(controller):
    await controller.goto(fixture_url("buttons.html"))

    client = FakeLLMClient(
        responses=[
            [_tool_use("t1", "click", {"element_id": 0})],
            [_tool_use("t2", "finish_task", {"summary": "Done.", "success": True})],
        ]
    )

    loop = AgentLoop(controller.page, client=client, max_steps=5, vision=False)
    result = await loop.run("Click the counter button once.")
    assert result.success is True

    # Initial observation has no image block either.
    first_call_messages = client.calls[0]
    assert all(block["type"] != "image" for block in first_call_messages[0]["content"])

    second_call_messages = client.calls[1]
    tool_result = second_call_messages[-1]["content"][0]
    assert [block["type"] for block in tool_result["content"]] == ["text", "text"]


async def test_loop_update_notes_persists_across_steps(controller):
    await controller.goto(fixture_url("buttons.html"))

    client = FakeLLMClient(
        responses=[
            [_tool_use("t1", "update_notes", {"notes": "Plan: click counter once, then finish."})],
            [_tool_use("t2", "click", {"element_id": 0})],
            [_tool_use("t3", "finish_task", {"summary": "Done.", "success": True})],
        ]
    )

    loop = AgentLoop(controller.page, client=client, max_steps=5, vision=False)
    events = []
    result = await loop.run("Click the counter button once.", on_step=events.append)

    assert result.success is True
    assert events[0].tool_name == "update_notes"
    assert events[0].tool_output == "Notes updated."
    assert loop.notes == "Plan: click counter once, then finish."

    # update_notes itself must not have triggered a browser action - only
    # the later "click" tool call should have incremented the counter.
    counter_text = await controller.page.text_content("#counter")
    assert counter_text == "Count: 1"

    # Subsequent calls to the LLM include the notes in the system prompt.
    assert "Plan: click counter once, then finish." in client.systems[1]
    assert "Plan: click counter once, then finish." in client.systems[2]

    # update_notes still produced a tool_result/observation for the next turn.
    second_call_messages = client.calls[1]
    tool_result = second_call_messages[-1]["content"][0]
    assert tool_result["tool_use_id"] == "t1"
    assert tool_result["content"][0] == {"type": "text", "text": "Notes updated."}


async def test_loop_handles_ask_user(controller):
    await controller.goto(fixture_url("simple_form.html"))

    client = FakeLLMClient(
        responses=[
            [_tool_use("t1", "ask_user", {"question": "What should I search for?"})],
            [_tool_use("t2", "finish_task", {"summary": "Done.", "success": True})],
        ]
    )

    async def fake_ask_user(question):
        assert question == "What should I search for?"
        return "playwright"

    loop = AgentLoop(controller.page, client=client, max_steps=5, ask_user=fake_ask_user)
    events = []
    result = await loop.run("Search for something.", on_step=events.append)

    assert result.success is True
    assert events[0].ask_user_question == "What should I search for?"

    second_call_messages = client.calls[1]
    tool_result_message = second_call_messages[-1]
    tool_result = tool_result_message["content"][0]
    assert tool_result["tool_use_id"] == "t1"
    assert tool_result["content"] == [{"type": "text", "text": "playwright"}]


async def test_loop_follows_link_opened_in_new_tab(controller):
    await controller.goto(fixture_url("article.html"))

    client = FakeLLMClient(
        responses=[
            [_tool_use("t1", "click", {"element_id": 0})],
            [_tool_use("t2", "finish_task", {"summary": "Opened the form.", "success": True})],
        ]
    )

    loop = AgentLoop(controller.page, client=client, max_steps=5, vision=False)
    result = await loop.run("Open the form link.")

    assert result.success is True
    assert "simple_form.html" in loop.page.url
    assert loop.page is not controller.page


async def test_loop_reaches_max_steps(controller):
    await controller.goto(fixture_url("buttons.html"))

    # Always click the counter, never finish.
    click = [_tool_use("t", "click", {"element_id": 0})]
    client = FakeLLMClient(responses=[click, click, click])

    loop = AgentLoop(controller.page, client=client, max_steps=3)
    result = await loop.run("Click forever.")

    assert result.success is False
    assert result.steps == 3
    assert "maximum number of steps" in result.summary
