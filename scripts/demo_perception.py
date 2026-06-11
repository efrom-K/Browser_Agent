"""Stage 1 demo: open a real page, capture set-of-marks state, save annotated screenshot."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from agent.browser.controller import BrowserController
from agent.browser.perception import capture_state, format_elements

RUNS_DIR = Path(__file__).resolve().parent.parent / "runs"


async def main() -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    async with BrowserController(headless=False) as ctrl:
        await ctrl.goto("https://www.wikipedia.org")
        state = await capture_state(ctrl.page)

        print(f"URL: {state.url}")
        print(f"Title: {state.title}")
        print(f"Found {len(state.elements)} interactive elements:\n")
        print(format_elements(state.elements))

        out_path = RUNS_DIR / "demo_perception.png"
        out_path.write_bytes(state.screenshot)
        print(f"\nAnnotated screenshot saved to {out_path}")

        await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
