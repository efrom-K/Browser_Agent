"""Interactive CLI for the browser agent.

Opens a visible Chromium window and a terminal prompt. Type a task, watch
the agent perceive the page, choose tools, and act on it in the browser.
Type 'exit' (or Ctrl+C) to close.

Run with:
    python scripts/run_agent.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from agent.browser.controller import BrowserController
from agent.core.loop import AgentLoop, StepEvent

# Persistent profile so logins (hh.ru, mail, delivery sites, etc.) survive
# across runs - log in once in the opened browser window and the session
# cookies will still be there next time.
PROFILE_DIR = Path(__file__).resolve().parent.parent / ".agent_profile"


def print_step(event: StepEvent) -> None:
    print(f"\n--- Step {event.step} ---")
    if event.assistant_text:
        print(f"Agent: {event.assistant_text.strip()}")
    print(f"Tool: {event.tool_name}({event.tool_input})")
    print(f"Result: {event.tool_output}")


async def main() -> None:
    print("Starting browser...")
    async with BrowserController(headless=False, user_data_dir=str(PROFILE_DIR)) as ctrl:
        await ctrl.page.goto("about:blank")
        loop = AgentLoop(ctrl.page)

        print("Ready. Type a task and press Enter (or 'exit' to quit).\n")
        while True:
            task = (await asyncio.to_thread(input, "Task> ")).strip()
            if not task:
                continue
            if task.lower() in ("exit", "quit"):
                break

            loop.messages = []  # start a fresh conversation for each task
            result = await loop.run(task, on_step=print_step)

            print("\n=== Done ===")
            print(f"Success: {result.success}")
            print(f"Steps: {result.steps}")
            print(f"Summary: {result.summary}\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
