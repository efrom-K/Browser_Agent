"""Turn a PageState into the content blocks Claude expects for one turn."""

from __future__ import annotations

import base64

from ..browser.perception import PageState, format_elements


def _page_description(state: PageState, tab_count: int | None = None) -> str:
    elements_text = format_elements(state.elements) or "(none)"
    lines = [f"Page: {state.title!r} ({state.url})"]
    if tab_count is not None:
        if tab_count > 1:
            lines.append(
                f"Open browser tabs: {tab_count} (this is the active one). "
                "Use close_tab to close extra tabs you no longer need."
            )
        else:
            lines.append("Open browser tabs: 1 (this one).")
    lines += [
        "Visible interactive elements:",
        elements_text,
        "Choose the next action.",
    ]
    return "\n".join(lines)


def build_observation_content(
    state: PageState, include_screenshot: bool = True, tab_count: int | None = None
) -> list[dict]:
    """Build the text (+ optional screenshot) content blocks describing the page.

    `include_screenshot` controls whether the annotated screenshot is sent to
    the LLM as an image block. Disable this for models that don't support
    (or don't reliably use) image input - the text element list is then the
    model's only view of the page.

    `tab_count` is the number of currently open browser tabs, if known - this
    is surfaced to the model so it notices stray tabs (e.g. opened by a click
    it didn't expect) and can close them with close_tab.
    """
    blocks: list[dict] = [{"type": "text", "text": _page_description(state, tab_count)}]

    if include_screenshot:
        image_b64 = base64.b64encode(state.screenshot).decode("ascii")
        blocks.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": image_b64,
                },
            }
        )

    return blocks


def build_observation(
    state: PageState,
    task: str | None = None,
    include_screenshot: bool = True,
    tab_count: int | None = None,
) -> list[dict]:
    """Build a user-message content list: a text description + optional screenshot.

    If `task` is given, it is prepended as a reminder of the overall goal
    (used for the very first observation). Subsequent observations omit it -
    the task stays in the conversation history.
    """
    content = build_observation_content(state, include_screenshot=include_screenshot, tab_count=tab_count)
    if task is not None:
        content[0]["text"] = f"Task: {task}\n\n" + content[0]["text"]
    return content
