"""Execute a Claude tool_use call against the live page."""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

from .. import config
from ..browser import actions
from ..browser.controller import wait_until_settled
from ..browser.exceptions import ElementNotFoundError
from ..browser.perception import _JS_SOURCE

_READ_CHUNK = 4000
_LIST_CHUNK = 25


# Page-changing actions (they can load pages) are spaced out on real sites:
# bursts of page loads are what trips anti-bot rate limits like Avito's.
_PAGE_ACTIONS = {"navigate", "click", "go_back", "press_key"}
_last_page_action = 0.0


async def _pace(page: Page, url: str) -> None:
    global _last_page_action
    if url.startswith("http"):
        wait = _last_page_action + config.MIN_ACTION_INTERVAL - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        _last_page_action = time.monotonic()


def _same_page(a: str, b: str) -> bool:
    return a.split("#")[0].rstrip("/") == b.split("#")[0].rstrip("/")


async def _list_items(page: Page) -> list[str]:
    if not await page.evaluate("typeof window.__agentReadList === 'function'"):
        await page.evaluate(_JS_SOURCE)
    return await page.evaluate("window.__agentReadList()")


@dataclass
class ToolResult:
    output: str
    finished: bool = False
    success: bool | None = None
    ask_user_question: str | None = None
    new_page: Page | None = None


async def execute_tool(
    page: Page, name: str, tool_input: dict, preferred_page: Page | None = None
) -> ToolResult:
    try:
        if name in _PAGE_ACTIONS or (name == "type_text" and tool_input.get("submit")):
            await _pace(page, tool_input.get("url") or page.url)

        if name == "navigate":
            if _same_page(tool_input["url"], page.url):
                # Re-loading the current page only costs a request; small
                # models do it when unsure what to do next.
                return ToolResult(output=f"Already on {page.url} - nothing reloaded.")
            await page.goto(tool_input["url"], wait_until="domcontentloaded")
            await wait_until_settled(page)
            return ToolResult(output=f"Navigated to {page.url}")

        if name == "click":
            context = page.context
            pages_before = set(context.pages)
            await actions.click(page, tool_input["element_id"])
            await page.wait_for_timeout(300)
            new_pages = [p for p in context.pages if p not in pages_before]
            if not new_pages:
                # Some sites open the new tab with a short delay, and a
                # plain click can also trigger in-page updates (AJAX,
                # re-renders) - this single wait covers both cases without
                # waiting twice.
                await wait_until_settled(page, timeout=3000)
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
            return ToolResult(output=f"Clicked element {tool_input['element_id']}")

        if name == "close_tab":
            context = page.context
            if len(context.pages) <= 1:
                return ToolResult(output="Error: cannot close the only open tab.")
            other_pages = [p for p in context.pages if p != page]
            # Prefer the tab we came from (tracked by the caller), so a
            # chain of "click vacancy -> new tab -> close_tab" returns to
            # the search results even if other background tabs are open.
            if preferred_page is not None and preferred_page in other_pages:
                new_page = preferred_page
            else:
                new_page = other_pages[-1]
            await page.close()
            await new_page.bring_to_front()
            return ToolResult(
                output=f"Closed tab. Now viewing {new_page.url} ({len(context.pages)} tabs open)",
                new_page=new_page,
            )

        if name == "read_list":
            items = await _list_items(page)
            if not items:
                return ToolResult(output="No repeated list of items found on this page - use read_page_text.")
            # Same auto-continue as read_page_text, counted in items.
            last_key, last_end = getattr(page, "_agent_list", (None, 0))
            if last_key == page.url and last_end >= len(items):
                page._agent_list = (page.url, 0)  # a further call starts over
                return ToolResult(
                    output=f"You have already read all {len(items)} items of this list. Choose "
                    "from them now (they are in your notes / the read_list results above), "
                    "or open the next results page for more."
                )
            start = last_end if last_key == page.url else 0
            end = min(start + _LIST_CHUNK, len(items))
            page._agent_list = (page.url, end)
            lines = [f"List of {len(items)} items on this page (items #{start + 1}-#{end}):"]
            lines += [f"#{i} {item}" for i, item in enumerate(items[start:end], start + 1)]
            if end < len(items):
                lines.append(f"(call read_list again for items #{end + 1}-#{min(end + _LIST_CHUNK, len(items))})")
            else:
                lines.append("(end of list on this page - for more items go to the next results page)")
            lines.append(
                "Note: this is dropped from your context after a few steps - choose the items "
                "you want now with pick_items (by number)."
            )
            return ToolResult(output="\n".join(lines))

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
            text = re.sub(r"\s*\n\s*", "\n", re.sub(r"[ \t\xa0]+", " ", text)).strip()
            # Calling again without an offset continues where the last read of
            # the same page/element stopped - small models just re-call it
            # expecting "more" rather than passing offsets.
            key = (page.url, element_id)
            start = tool_input.get("offset")
            if start is None:
                last_key, last_end = getattr(page, "_agent_read", (None, 0))
                start = last_end if last_key == key and last_end < len(text) else 0
            end = start + _READ_CHUNK
            page._agent_read = (key, end)
            chunk = text[start:end]
            if end < len(text):
                chunk += (
                    f"\n... (chars {start}-{end} of {len(text)}; call read_page_text "
                    "again to continue reading)"
                )
            elif start > 0:
                chunk += "\n(end of page text)"
            elif text:
                chunk += "\n(this is the complete text of the page as currently loaded)"
            if end < len(text) and element_id is None:
                n = len(await _list_items(page))
                if n:
                    chunk += f"\nTip: this page has a list of {n} items - read_list shows them compactly."
            if len(chunk) > 1000:
                chunk += (
                    "\nNote: this text is dropped from your context after a few steps - "
                    "save anything you need (e.g. candidates and their key facts) with update_notes."
                )
            return ToolResult(output=chunk or "(empty)")

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
        # Small models reuse IDs from an older page; tell them the valid range.
        try:
            count = await page.evaluate("(window.__agentElements || []).length")
        except PlaywrightError:
            count = 0
        valid = f"the current element list only has IDs 0-{count - 1}" if count else "the page has no elements now"
        return ToolResult(
            output=f"Error: {exc} - {valid}. IDs from earlier pages are no longer valid; "
            "pick an ID from the latest element list."
        )

    except PlaywrightError as exc:
        # Catch-all for browser-level failures (navigation timeouts, no
        # history to go back to, detached elements, etc.) so a single bad
        # action doesn't crash the whole run - the agent sees the error and
        # can adapt.
        message = str(exc).splitlines()[0]
        return ToolResult(output=f"Error: {message}")
