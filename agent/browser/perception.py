"""Set-of-marks perception: turn the live DOM into a numbered list of
interactive elements plus an annotated screenshot, without relying on any
hardcoded selectors or page-specific knowledge."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

_JS_PATH = Path(__file__).with_name("perception.js")
_JS_SOURCE = _JS_PATH.read_text(encoding="utf-8")


@dataclass
class ElementInfo:
    id: int
    tag: str
    role: str
    type: str
    name: str
    disabled: bool
    bbox: dict


@dataclass
class PageState:
    url: str
    title: str
    elements: list[ElementInfo]
    screenshot: bytes


async def capture_state(page: Page, mark_screenshot: bool = True) -> PageState:
    """Scan the page for interactive elements and capture a screenshot.

    Re-injects the perception script and re-scans the DOM every call, so the
    returned element IDs are only valid until the next action mutates the page.
    """
    try:
        return await _capture_state_once(page, mark_screenshot)
    except PlaywrightError as exc:
        # The previous action may have triggered a navigation that was still
        # in flight, destroying the JS execution context mid-scan. Wait for
        # the new page to settle and try once more.
        if "context was destroyed" not in str(exc).lower():
            raise
        await page.wait_for_load_state("domcontentloaded")
        return await _capture_state_once(page, mark_screenshot)


async def _capture_state_once(page: Page, mark_screenshot: bool) -> PageState:
    await page.evaluate(_JS_SOURCE)
    descriptors = await page.evaluate("window.__agentCollect()")

    screenshot: bytes = b""
    if mark_screenshot:
        await page.evaluate("window.__agentShowMarks()")
        try:
            screenshot = await page.screenshot()
        finally:
            await page.evaluate("window.__agentRemoveMarks()")

    elements = [ElementInfo(id=i, **d) for i, d in enumerate(descriptors)]
    return PageState(
        url=page.url,
        title=await page.title(),
        elements=elements,
        screenshot=screenshot,
    )


def format_elements(elements: list[ElementInfo]) -> str:
    """Render elements as a compact text list for the LLM prompt."""
    lines = []
    for el in elements:
        attrs = []
        if el.type:
            attrs.append(f' type="{el.type}"')
        if el.role:
            attrs.append(f' role="{el.role}"')
        if el.disabled:
            attrs.append(" disabled")
        line = f"[{el.id}] <{el.tag}{''.join(attrs)}>"
        if el.name:
            line += f' "{el.name}"'
        lines.append(line)
    return "\n".join(lines)
