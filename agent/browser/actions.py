"""Execute actions against elements identified by the numeric IDs that
`perception.capture_state` assigned during the most recent scan.

Clicking and typing go through real mouse/keyboard events (not
`element.click()` / `element.value =`) so that JS event listeners on the
page (React, vanilla `addEventListener`, etc.) fire normally.
"""

from __future__ import annotations

from playwright.async_api import Page

from .exceptions import ElementNotFoundError

_GET_RECT_JS = """(id) => {
    const el = window.__agentElements && window.__agentElements[id];
    if (!el) return null;
    el.scrollIntoView({block: 'center', inline: 'center'});
    const r = el.getBoundingClientRect();
    return { x: r.x, y: r.y, width: r.width, height: r.height };
}"""


async def _element_center(page: Page, element_id: int) -> tuple[float, float]:
    rect = await page.evaluate(_GET_RECT_JS, element_id)
    if rect is None:
        raise ElementNotFoundError(element_id)
    return rect["x"] + rect["width"] / 2, rect["y"] + rect["height"] / 2


async def click(page: Page, element_id: int) -> None:
    x, y = await _element_center(page, element_id)
    await page.mouse.click(x, y)


async def type_text(page: Page, element_id: int, text: str, submit: bool = False) -> None:
    x, y = await _element_center(page, element_id)
    await page.mouse.click(x, y)
    await page.keyboard.press("Control+A")
    await page.keyboard.press("Delete")
    await page.keyboard.type(text, delay=20)
    if submit:
        await page.keyboard.press("Enter")


async def scroll(page: Page, direction: str = "down", amount: int = 600) -> None:
    dy = amount if direction == "down" else -amount
    await page.mouse.wheel(0, dy)
    # Let layout/scroll settle before the next perception scan reads bounding boxes.
    await page.wait_for_timeout(200)


async def press_key(page: Page, key: str) -> None:
    await page.keyboard.press(key)
