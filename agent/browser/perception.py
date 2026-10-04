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

# Bot checks: a captcha widget iframe, or the page text saying so. The agent
# must hand these to the user rather than try to get past them.
_CAPTCHA_JS = r"""() => {
  // Only visible widgets count: many normal pages embed an invisible (0x0)
  // reCAPTCHA/Turnstile frame that never challenges the user.
  const widget = [...document.querySelectorAll('iframe')].some(f => /captcha|challenge|geetest/i.test(f.src) &&
    f.getBoundingClientRect().width >= 50 && f.getBoundingClientRect().height >= 50);
  // Bot-check pages are short; on a normal page the words may just be content
  // (a search result or repo titled "... captchas").
  const re = /captcha|капч|не робот|not a robot|доступ ограничен|подтвердите, что вы|проблема с IP|не так с IP|много запросов|too many requests/i;
  const body = document.body?.innerText || '';
  return widget || (body.length < 2000 && re.test(document.title + ' ' + body));
}"""


@dataclass
class ElementInfo:
    id: int
    tag: str
    role: str
    type: str
    name: str
    disabled: bool
    bbox: dict
    href: str = ""
    next_page: bool = False  # the page's "next results page" control
    search_box: bool = False  # the site's search field


@dataclass
class PageState:
    url: str
    title: str
    elements: list[ElementInfo]
    screenshot: bytes
    captcha: bool = False
    list_items: int = 0  # size of the page's main repeated item list, if any
    next_href: str = ""  # next-page link that exists only in a hidden layout copy


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
        captcha=await page.evaluate(_CAPTCHA_JS),
        list_items=await page.evaluate("window.__agentListCount()"),
        next_href=await page.evaluate("window.__agentNextHref || ''"),
    )


def short_href(href: str) -> str:
    """Drop long query params (tracking noise like context=H4sI...) but keep
    short ones, which often identify the target (item?id=123, p=2)."""
    path, _, query = href.partition("?")
    kept = [p for p in query.split("&") if p and len(p) <= 40]
    return (path + "?" + "&".join(kept) if kept else path)[:120]


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
        if el.href and not el.href.startswith(("#", "javascript:")):
            line += f" -> {short_href(el.href)}"
        if el.next_page:
            line += " (next page)"
        if el.search_box:
            line += " (search box)"
        lines.append(line)
    return "\n".join(lines)
