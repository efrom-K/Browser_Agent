"""Run a fixed set of real-site tasks and report success / steps / time / tokens.

Used to tune the agent for small local models: change something, re-run,
compare. Each task has a check on the final summary (or page) so "success"
means the right answer, not just the model claiming it finished.

Run with:
    python scripts/bench.py            # all tasks
    python scripts/bench.py books form # tasks whose name contains a substring
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import config
from agent.browser.controller import BrowserController
from agent.core.llm_client import LLMClient
from agent.core.loop import AgentLoop

TASKS = [
    (
        "books_category",
        "Go to https://books.toscrape.com, open the 'Travel' category and tell me how many books it has.",
        lambda summary, page: "11" in summary,
    ),
    (
        "books_price",
        "On https://books.toscrape.com find the book 'The Black Maria' and tell me its price.",
        lambda summary, page: "52.15" in summary,
    ),
    (
        "quotes_page2",
        "Go to https://quotes.toscrape.com, go to the second page of quotes and tell me the author of the first quote there.",
        lambda summary, page: "marilyn" in summary.lower(),
    ),
    (
        "wiki_search",
        "Using the search box on https://en.wikipedia.org, find the article about the Python programming language and tell me who designed it.",
        lambda summary, page: "guido" in summary.lower(),
    ),
    (
        "form",
        "Go to https://httpbin.org/forms/post and order a large pizza with bacon for customer 'Ivan Petrov', phone 555-1234, then submit the form.",
        lambda summary, page: "Ivan Petrov" in page and '"size": "large"' in page and "bacon" in page,
    ),
]


class CountingClient(LLMClient):
    def __init__(self):
        super().__init__()
        self.input_tokens = []

    async def step(self, *args, **kwargs):
        response = await super().step(*args, **kwargs)
        self.input_tokens.append(response.usage.input_tokens)
        return response


async def run_task(name, task, check):
    async with BrowserController(headless=True) as ctrl:
        client = CountingClient()
        loop = AgentLoop(ctrl.page, client=client, max_steps=20)
        start = time.monotonic()
        try:
            result = await loop.run(task, on_step=lambda e: print(f"  {e.step}. {e.tool_name}({e.tool_input})"))
            page_text = await loop.page.evaluate("document.body.innerText")
            ok = result.success and check(result.summary, page_text)
            summary, steps = result.summary, result.steps
        except Exception as exc:  # noqa: BLE001 - a crash is a failed task
            ok, summary, steps = False, f"CRASH: {exc!r}", len(client.input_tokens)
        elapsed = time.monotonic() - start
    tokens = client.input_tokens
    print(
        f"[{'PASS' if ok else 'FAIL'}] {name}: {steps} steps, {elapsed:.0f}s, "
        f"max prompt {max(tokens, default=0)} tok, avg {sum(tokens) // max(len(tokens), 1)} tok\n"
        f"  summary: {summary[:200]}"
    )
    return ok, steps, elapsed


async def main():
    filters = sys.argv[1:]
    tasks = [t for t in TASKS if not filters or any(f in t[0] for f in filters)]
    print(f"Model: {config.LLM_MODEL} (local={config.LOCAL}, vision={config.VISION_ENABLED})")
    results = [await run_task(*t) for t in tasks]
    passed = sum(ok for ok, _, _ in results)
    total_time = sum(t for _, _, t in results)
    print(f"\n{passed}/{len(results)} passed, {total_time:.0f}s total")


if __name__ == "__main__":
    asyncio.run(main())
