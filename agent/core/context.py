"""Context management: keep the conversation from growing without bound.

Each step appends a tool_result observation (the dispatcher's action result
plus a fresh page description, and a screenshot when vision is enabled).
Over a long task these add up quickly. `trim_history` replaces the page
description/screenshot of older observations with a short placeholder,
keeping only the most recent ones in full - the agent's own reasoning and
the sequence of actions it took (the assistant messages) are never trimmed,
so it doesn't lose track of what it already did.
"""

from __future__ import annotations

from .. import config

_OMITTED_TEXT = "[older page observation omitted to save context]"


def trim_history(messages: list[dict], keep_last: int | None = None) -> list[dict]:
    """Return a copy of `messages` with old tool_result observations trimmed.

    The most recent `keep_last` observations are left untouched. Everything
    else (assistant messages, the very first observation, tool_result
    messages from ask_user) is returned as-is.
    """
    keep_last = config.CONTEXT_KEEP_LAST if keep_last is None else keep_last

    observation_indices = [i for i, msg in enumerate(messages) if i > 0 and _is_observation(msg)]
    trim_indices = observation_indices[:-keep_last] if keep_last > 0 else observation_indices
    if not trim_indices:
        return messages

    trimmed = list(messages)
    for i in trim_indices:
        trimmed[i] = _trim_observation(trimmed[i])
    return trimmed


def _is_observation(message: dict) -> bool:
    if message["role"] != "user" or not isinstance(message["content"], list):
        return False
    if not message["content"]:
        return False
    block = message["content"][0]
    # An observation's tool_result content is [action result, page
    # description, (screenshot)]; ask_user replies are a single text block.
    return block.get("type") == "tool_result" and len(block.get("content", [])) > 1


def _trim_observation(message: dict) -> dict:
    tool_result = message["content"][0]
    action_result = tool_result["content"][0]
    new_tool_result = {
        **tool_result,
        "content": [action_result, {"type": "text", "text": _OMITTED_TEXT}],
    }
    return {**message, "content": [new_tool_result]}
