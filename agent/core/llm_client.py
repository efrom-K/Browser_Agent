"""Thin async wrapper around the Anthropic Messages API."""

from __future__ import annotations

import asyncio

from anthropic import Anthropic
from anthropic.types import Message

from .. import config


class LLMClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ):
        self._client = Anthropic(
            api_key=api_key or config.LLM_API_KEY,
            base_url=base_url or config.LLM_BASE_URL,
        )
        self.model = model or config.LLM_MODEL

    async def step(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 1024,
        retries: int = 2,
    ) -> Message:
        """Run one turn of the conversation and return the raw Message.

        The Anthropic SDK is synchronous; the call is offloaded to a thread so
        it doesn't block the asyncio event loop that Playwright runs on. Free
        LLM endpoints occasionally hang on a request without erroring, so a
        per-call timeout with a few retries keeps the agent loop moving.
        """
        for attempt in range(retries + 1):
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(
                        self._client.messages.create,
                        model=self.model,
                        max_tokens=max_tokens,
                        system=system,
                        messages=messages,
                        tools=tools,
                    ),
                    timeout=config.LLM_TIMEOUT,
                )
            except asyncio.TimeoutError:
                if attempt == retries:
                    raise
