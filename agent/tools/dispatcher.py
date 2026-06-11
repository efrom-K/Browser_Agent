"""Execute a Claude tool_use call against the live page."""

from __future__ import annotations

from dataclasses import dataclass

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

from ..browser import actions
from ..browser.controller import wait_until_settled
from ..browser.exceptions import ElementNotFoundError


@dataclass
class ToolResult:
    output: str
    finished: bool = False
    success: bool | None = None
    ask_user_question: str | None = None
    new_page: Page | None = None


async def execute_tool(page: Page, name: str, tool_input: dict) -> ToolResult:
    try:
        if name == "navigate":
            await page.goto(tool_input["url"], wait_until="domcontentloaded")
            await wait_until_settled(page)
            return ToolResult(output=f"Navigated to {page.url}")

        if name == "click":
            context = page.context
            pages_before = set(context.pages)
            await actions.click(page, tool_input["element_id"])
            await page.wait_for_timeout(300)
            new_pages = [p for p in context.pages if p not in pages_before]
            if new_pages:
                new_page = new_pages[-1]
                await new_page.wait_for_load_state("domcontentloaded")
                await wait_until_settled(new_page)
                return ToolResult(
                    output=(
                        f"Clicked element {tool_input['element_id']}. This opened a "
                        f"new tab ({len(context.pages)} tabs open) - now viewing it. "
                        "Use close_tab to return to the previous tab when done."
                    ),
                    new_page=new_page,
                )
            await wait_until_settled(page)
            return ToolResult(output=f"Clicked element {tool_input['element_id']}")

        if name == "close_tab":
            context = page.context
            if len(context.pages) <= 1:
                return ToolResult(output="Error: cannot close the only open tab.")
            other_pages = [p for p in context.pages if p != page]
            await page.close()
            new_page = other_pages[-1]
            await new_page.bring_to_front()
            return ToolResult(
                output=f"Closed tab. Now viewing {new_page.url} ({len(context.pages)} tabs open)",
                new_page=new_page,
            )

        if name == "read_page_text":
            element_id = tool_input.get("element_id")
            if element_id is not None:
                text = await page.evaluate(
                    "(id) => { const el = window.__agentElements && "
                    "window.__agentElements[id]; return el ? "
                    "(el.innerText || el.textContent || '') : null; }",
                    element_id,
                )
                if text is None:
                    raise ElementNotFoundError(element_id)
            else:
                text = await page.evaluate("document.body.innerText")
            text = text.strip()
            max_chars = 4000
            if len(text) > max_chars:
                text = text[:max_chars] + "\n... (truncated)"
            return ToolResult(output=text or "(empty)")

        if name == "type_text":
            await actions.type_text(
                page,
                tool_input["element_id"],
                tool_input["text"],
                submit=tool_input.get("submit", False),
            )
            return ToolResult(
                output=f"Typed {tool_input['text']!r} into element {tool_input['element_id']}"
                + (" and pressed Enter" if tool_input.get("submit") else "")
            )

        if name == "scroll":
            await actions.scroll(
                page,
                direction=tool_input.get("direction", "down"),
                amount=tool_input.get("amount", 600),
            )
            return ToolResult(output=f"Scrolled {tool_input.get('direction', 'down')}")

        if name == "press_key":
            await actions.press_key(page, tool_input["key"])
            return ToolResult(output=f"Pressed key {tool_input['key']}")

        if name == "go_back":
            await page.go_back(wait_until="domcontentloaded")
            await wait_until_settled(page)
            return ToolResult(output=f"Went back to {page.url}")

        if name == "ask_user":
            return ToolResult(
                output="Waiting for user input.",
                ask_user_question=tool_input["question"],
            )

        if name == "finish_task":
            return ToolResult(
                output=tool_input["summary"],
                finished=True,
                success=tool_input.get("success", True),
            )

        return ToolResult(output=f"Unknown tool: {name}")

    except ElementNotFoundError as exc:
        return ToolResult(
            output=f"Error: {exc}. The page may have changed - re-check the latest screenshot."
        )

    except PlaywrightError as exc:
        # Catch-all for browser-level failures (navigation timeouts, no
        # history to go back to, detached elements, etc.) so a single bad
        # action doesn't crash the whole run - the agent sees the error and
        # can adapt.
        message = str(exc).splitlines()[0]
        return ToolResult(output=f"Error: {message}")
