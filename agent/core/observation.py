"""Turn a PageState into the content blocks Claude expects for one turn."""

from __future__ import annotations

import base64

from ..browser.perception import PageState, format_elements


def _page_description(state: PageState) -> str:
    elements_text = format_elements(state.elements) or "(none)"
    return "\n".join(
        [
            f"Page: {state.title!r} ({state.url})",
            "Visible interactive elements:",
            elements_text,
            "Choose the next action.",
        ]
    )


def build_observation_content(state: PageState, include_screenshot: bool = True) -> list[dict]:
    """Build the text (+ optional screenshot) content blocks describing the page.

    `include_screenshot` controls whether the annotated screenshot is sent to
    the LLM as an image block. Disable this for models that don't support
    (or don't reliably use) image input - the text element list is then the
    model's only view of the page.
    """
    blocks: list[dict] = [{"type": "text", "text": _page_description(state)}]

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
    state: PageState, task: str | None = None, include_screenshot: bool = True
) -> list[dict]:
    """Build a user-message content list: a text description + optional screenshot.

    If `task` is given, it is prepended as a reminder of the overall goal
    (used for the very first observation). Subsequent observations omit it -
    the task stays in the conversation history.
    """
    content = build_observation_content(state, include_screenshot=include_screenshot)
    if task is not None:
        content[0]["text"] = f"Task: {task}\n\n" + content[0]["text"]
    return content
