"""The perceive -> decide -> act loop that drives the agent through a task."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from playwright.async_api import Page

from .. import config
from ..browser.perception import capture_state
from ..tools.dispatcher import ToolResult, execute_tool
from ..tools.schema import TOOLS
from .context import trim_history
from .llm_client import LLMClient
from .observation import build_observation, build_observation_content
from .prompts import build_system_prompt


@dataclass
class StepEvent:
    """Reported to `on_step` after each tool call so a UI can display it."""

    step: int
    assistant_text: str | None
    tool_name: str
    tool_input: dict
    tool_output: str
    finished: bool = False
    success: bool | None = None
    ask_user_question: str | None = None


@dataclass
class AgentResult:
    success: bool
    summary: str
    steps: int


AskUserFn = Callable[[str], Awaitable[str]]
OnStepFn = Callable[[StepEvent], object]


async def _default_ask_user(question: str) -> str:
    return await asyncio.to_thread(input, f"\n[agent asks] {question}\n> ")


def _content_to_param(blocks) -> list[dict]:
    """Convert Anthropic response content blocks to message-param dicts."""
    result = []
    for block in blocks:
        if block.type == "text":
            result.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            result.append(
                {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
            )
    return result


async def _emit(on_step: OnStepFn | None, event: StepEvent) -> None:
    if on_step is None:
        return
    result = on_step(event)
    if asyncio.iscoroutine(result):
        await result


class AgentLoop:
    """Runs one task to completion against a single Playwright page."""

    def __init__(
        self,
        page: Page,
        client: LLMClient | None = None,
        max_steps: int | None = None,
        ask_user: AskUserFn = _default_ask_user,
        vision: bool | None = None,
    ):
        self.page = page
        self.client = client or LLMClient()
        self.max_steps = max_steps or config.MAX_STEPS
        self.ask_user = ask_user
        self.vision = config.VISION_ENABLED if vision is None else vision
        self.system_prompt = build_system_prompt(vision=self.vision)
        self.messages: list[dict] = []
        self.notes = ""

    def _current_system_prompt(self) -> str:
        if not self.notes:
            return self.system_prompt
        return f"{self.system_prompt}\n\nYour current notes:\n{self.notes}"

    async def run(self, task: str, on_step: OnStepFn | None = None) -> AgentResult:
        state = await capture_state(self.page, mark_screenshot=self.vision)
        self.messages.append(
            {"role": "user", "content": build_observation(state, task, include_screenshot=self.vision)}
        )

        for step in range(1, self.max_steps + 1):
            llm_messages = trim_history(self.messages)
            response = await self.client.step(self._current_system_prompt(), llm_messages, TOOLS)
            self.messages.append(
                {"role": "assistant", "content": _content_to_param(response.content)}
            )

            assistant_text = (
                "\n".join(b.text for b in response.content if b.type == "text") or None
            )
            tool_use = next((b for b in response.content if b.type == "tool_use"), None)

            if tool_use is None:
                self.messages.append(
                    {"role": "user", "content": "Choose one of the available tools to proceed."}
                )
                await _emit(
                    on_step,
                    StepEvent(
                        step=step,
                        assistant_text=assistant_text,
                        tool_name="(none)",
                        tool_input={},
                        tool_output="No tool call - prompted the model to continue.",
                    ),
                )
                continue

            if tool_use.name == "update_notes":
                self.notes = tool_use.input.get("notes", "")
                result = ToolResult(output="Notes updated.")
            else:
                result = await execute_tool(self.page, tool_use.name, tool_use.input)

            await _emit(
                on_step,
                StepEvent(
                    step=step,
                    assistant_text=assistant_text,
                    tool_name=tool_use.name,
                    tool_input=tool_use.input,
                    tool_output=result.output,
                    finished=result.finished,
                    success=result.success,
                    ask_user_question=result.ask_user_question,
                ),
            )

            if result.ask_user_question:
                answer = await self.ask_user(result.ask_user_question)
                self.messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_use.id,
                                "content": [{"type": "text", "text": answer}],
                            }
                        ],
                    }
                )
                continue

            if result.finished:
                return AgentResult(success=bool(result.success), summary=result.output, steps=step)

            if result.new_page is not None:
                self.page = result.new_page

            new_state = await capture_state(self.page, mark_screenshot=self.vision)
            tool_result_content = [
                {"type": "text", "text": result.output}
            ] + build_observation_content(new_state, include_screenshot=self.vision)
            self.messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use.id,
                            "content": tool_result_content,
                        }
                    ],
                }
            )

        return AgentResult(
            success=False,
            summary="Reached the maximum number of steps without finishing.",
            steps=self.max_steps,
        )
