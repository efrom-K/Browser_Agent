"""Live demo on hh.ru using the persistent profile created by
scripts/demo_hh_login.py.

Demonstrates: search results perception, following a vacancy link that opens
in a new tab (auto tab-switch), reading the full job description with
read_page_text, and returning to the search results with close_tab.

The task deliberately does NOT submit any application - it only reads and
summarizes, to avoid sending real responses to employers.

Run with:
    python scripts/demo_hh.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from agent.browser.controller import BrowserController
from agent.core.loop import AgentLoop, StepEvent

PROFILE_DIR = Path(__file__).resolve().parent.parent / ".hh_profile"

# Start directly on the search results page (rather than the busy,
# widget-heavy personalized homepage) to keep the element list manageable.
START_URL = "https://hh.ru/search/vacancy?text=AI+%D0%B8%D0%BD%D0%B6%D0%B5%D0%BD%D0%B5%D1%80"

TASK = (
    "Перед тобой результаты поиска вакансий 'AI инженер' на hh.ru. "
    "Открой первую подходящую вакансию (она откроется в новой вкладке), "
    "прочитай полное описание вакансии с помощью read_page_text, затем "
    "закрой эту вкладку (close_tab), чтобы вернуться к результатам поиска. "
    "ВАЖНО: ничего не отправляй и никуда не откликайся, не нажимай "
    "'Откликнуться'. Заверши задачу через finish_task с кратким описанием "
    "найденной вакансии (название, компания, ключевые требования)."
)


def print_step(event: StepEvent) -> None:
    print(f"\n--- Step {event.step} ---", flush=True)
    if event.assistant_text:
        print(f"Agent: {event.assistant_text.strip()}", flush=True)
    print(f"Tool: {event.tool_name}({event.tool_input})", flush=True)
    print(f"Result: {event.tool_output[:500]}", flush=True)


async def main() -> None:
    ctrl = BrowserController(headless=False, user_data_dir=str(PROFILE_DIR))
    await ctrl.start()
    try:
        print("Navigating to search results...", flush=True)
        await ctrl.goto(START_URL)
        print("Loaded. Starting agent loop...", flush=True)
        loop = AgentLoop(ctrl.page, max_steps=20)
        result = await loop.run(TASK, on_step=print_step)

        print("\n=== Done ===", flush=True)
        print(f"Success: {result.success}", flush=True)
        print(f"Steps: {result.steps}", flush=True)
        print(f"Summary: {result.summary}", flush=True)
    finally:
        await ctrl.close()


if __name__ == "__main__":
    asyncio.run(main())
