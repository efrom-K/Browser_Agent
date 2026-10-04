"""The perceive -> decide -> act loop that drives the agent through a task."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

from playwright.async_api import Page

from .. import config
from ..browser.perception import capture_state
from ..tools.dispatcher import ToolResult, _list_items, execute_tool
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


_MAX_REPEATS = 3
_MAX_SCROLLS = 6  # scrolling through a long list legitimately repeats

_NAVIGATE_REFUSED = (
    "Navigation refused: {url} is a guessed URL - it is neither a site's home page, "
    "nor in the task, nor linked from the current page. Open the site's home page "
    "(e.g. https://{host}) and use its search box, menus and filters instead."
)


def _url_key(url: str) -> tuple[str, str]:
    parts = urlsplit(url)
    return parts.netloc.lower().removeprefix("www."), parts.path.rstrip("/")


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
        # Tabs we've navigated away from via an auto-followed click, most
        # recent last - close_tab returns to the top of this stack.
        self._tab_stack: list[Page] = []
        # (tool name, input, output) of the last action and how many times in a row
        # it was repeated - small models get stuck re-issuing a failing call.
        self._last_call: tuple[str, str, str] | None = None
        self._repeats = 0
        # URLs navigate may open: from the task and the current page's links.
        # Small models otherwise guess deep URLs instead of using site search.
        self._known_urls: set[tuple[str, str]] = set()
        self._notes_streak = 0
        self._finish_checked = False
        # Items chosen with pick_items: exact lines from the page + absolute link,
        # so the final answer doesn't depend on the model copying them right.
        self.picked: list[str] = []

    def _with_notes(self, messages: list[dict]) -> list[dict]:
        """Attach the notes to the newest message rather than the system prompt.

        A changing system prompt invalidates the provider's prompt cache for the
        whole conversation; at the end it only costs the notes themselves.
        """
        notes = self.notes
        if self.picked:
            notes += f"\n\nPicked items so far ({len(self.picked)}):\n" + "\n".join(
                f"{i}. {line}" for i, line in enumerate(self.picked, 1)
            )
        if not notes:
            return messages
        last = messages[-1]
        content = last["content"]
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        block = {"type": "text", "text": f"Your current notes:\n{notes.strip()}"}
        return messages[:-1] + [{**last, "content": [*content, block]}]

    async def _pick_items(self, numbers: list[int]) -> ToolResult:
        items = await _list_items(self.page)
        bad = [n for n in numbers if not 1 <= n <= len(items)]
        if bad:
            return ToolResult(
                output=f"Error: no items {bad} in this page's list - it has items #1-#{len(items)}. "
                "Pass the #numbers that start each read_list line, not prices or counts from the text."
            )
        added = 0
        for n in numbers:
            title, _, href = items[n - 1].rpartition(" -> ")
            line = f"{title} -> {urljoin(self.page.url, href)}" if title else items[n - 1]
            if line not in self.picked:
                self.picked.append(line)
                added += 1
        return ToolResult(
            output=f"Picked {added} new item(s); {len(self.picked)} picked in total (shown in your notes). "
            "Their exact details and links will be included in your final answer automatically."
        )

    def _remember_links(self, state) -> None:
        self._known_urls.add(_url_key(state.url))
        if state.next_href:
            self._known_urls.add(_url_key(state.next_href))
        self._known_urls.update(_url_key(urljoin(state.url, el.href)) for el in state.elements if el.href)

    def _unknown_links(self, text: str) -> list[str]:
        known_paths = {path for _, path in self._known_urls}
        links = re.findall(r"https?://[^\s)\]>,;]+|(?<![\w./])/[\w\-.~%]+/[\w\-.~%/]+", text)
        return [link for link in links if _url_key(urljoin(self.page.url, link))[1] not in known_paths]

    def _may_navigate(self, url: str) -> bool:
        host, path = _url_key(url)
        return not path or (host, path) in self._known_urls

    async def run(self, task: str, on_step: OnStepFn | None = None) -> AgentResult:
        state = await capture_state(self.page, mark_screenshot=self.vision)
        self._known_urls = {_url_key(u) for u in re.findall(r"https?://[^\s'\"«»]+", task)}
        self._remember_links(state)
        self._finish_checked = False
        self._notes_streak = 0
        self.picked = []
        self.messages.append(
            {
                "role": "user",
                "content": build_observation(
                    state, task, include_screenshot=self.vision, tab_count=len(self.page.context.pages)
                ),
            }
        )

        for step in range(1, self.max_steps + 1):
            llm_messages = trim_history(self.messages)
            response = await self.client.step(self.system_prompt, self._with_notes(llm_messages), TOOLS)
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

            self._notes_streak = self._notes_streak + 1 if tool_use.name == "update_notes" else 0
            if tool_use.name == "update_notes":
                self.notes = tool_use.input.get("notes", "")
                result = ToolResult(output="Notes updated.")
                if self._notes_streak >= _MAX_REPEATS:
                    result.output += (
                        f"\nWARNING: you have rewritten your notes {self._notes_streak} times in a row "
                        "without acting. Stop rewriting them - take the next action now (if you "
                        "already have enough candidates, call finish_task with the result)."
                    )
            elif tool_use.name == "pick_items":
                result = await self._pick_items(tool_use.input.get("item_numbers", []))
            elif tool_use.name == "finish_task" and not self._finish_checked and (
                bad := self._unknown_links(tool_use.input.get("summary", ""))
            ):
                # Small models garble links when copying them; send it back once.
                self._finish_checked = True
                result = ToolResult(
                    output="Not finished yet: these links in your summary do not exist on any page "
                    f"you have seen: {', '.join(bad)}. Copy each link exactly from the read_list / "
                    "element list output (or your notes) and call finish_task again."
                )
            elif tool_use.name == "navigate" and not self._may_navigate(tool_use.input.get("url", "")):
                url = tool_use.input.get("url", "")
                result = ToolResult(output=_NAVIGATE_REFUSED.format(url=url, host=_url_key(url)[0]))
            elif tool_use.name == "close_tab":
                preferred_page = self._tab_stack[-1] if self._tab_stack else None
                result = await execute_tool(
                    self.page, tool_use.name, tool_use.input, preferred_page=preferred_page
                )
                if result.new_page is not None and self._tab_stack:
                    self._tab_stack.pop()
            else:
                result = await execute_tool(self.page, tool_use.name, tool_use.input)

            # Same call with the same result: paging tools (read_list, ...) repeat
            # the call legitimately but get new output each time.
            call = (tool_use.name, repr(tool_use.input), result.output)
            self._repeats = self._repeats + 1 if call == self._last_call else 1
            self._last_call = call
            if self._repeats >= (_MAX_SCROLLS if tool_use.name == "scroll" else _MAX_REPEATS):
                result.output += (
                    f"\nWARNING: you have made this exact same call {self._repeats} times in a row. "
                    "It is not getting you closer to the goal - stop repeating it and try a "
                    "different approach (e.g. the site's search box, a different element, go back; "
                    "to go through a long list, use read_page_text instead of scrolling)."
                )

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
                summary = result.output
                if self.picked:
                    summary += "\n\nPicked items (exact data from the site):\n" + "\n".join(
                        f"{i}. {line}" for i, line in enumerate(self.picked, 1)
                    )
                return AgentResult(success=bool(result.success), summary=summary, steps=step)

            if result.new_page is not None:
                if tool_use.name == "click":
                    self._tab_stack.append(self.page)
                self.page = result.new_page

            if tool_use.name == "read_list":
                self._known_urls.update(
                    _url_key(urljoin(self.page.url, href))
                    for href in re.findall(r" -> (\S+)$", result.output, re.M)
                )

            if self.page.is_closed():
                # The site (or the user) closed our tab: fall back to where we
                # came from, else the most recent open tab.
                while self._tab_stack and self.page.is_closed():
                    self.page = self._tab_stack.pop()
                if self.page.is_closed():
                    self.page = self.page.context.pages[-1]
                await self.page.bring_to_front()
                result.output += f"\nThe tab was closed; now viewing {self.page.url}."

            new_state = await capture_state(self.page, mark_screenshot=self.vision)
            self._remember_links(new_state)
            tool_result_content = [
                {"type": "text", "text": result.output}
            ] + build_observation_content(
                new_state, include_screenshot=self.vision, tab_count=len(self.page.context.pages)
            )
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
