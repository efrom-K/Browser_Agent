import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from agent.browser.controller import BrowserController
from agent.browser.perception import capture_state, format_elements
from agent.core.llm_client import LLMClient
from agent.core.observation import build_observation
from agent.core.prompts import build_system_prompt

PROFILE_DIR = Path(__file__).resolve().parent.parent / ".hh_profile"
START_URL = "https://hh.ru/search/vacancy?text=AI+%D0%B8%D0%BD%D0%B6%D0%B5%D0%BD%D0%B5%D1%80"


async def main():
    ctrl = BrowserController(headless=True, user_data_dir=str(PROFILE_DIR))
    await ctrl.start()
    try:
        await ctrl.goto(START_URL)
        state = await capture_state(ctrl.page, mark_screenshot=False)
        print(f"num elements: {len(state.elements)}")
        text = format_elements(state.elements)
        print(f"element list chars: {len(text)}")

        obs = build_observation(state, "test task", include_screenshot=False)
        print(f"observation content blocks: {len(obs)}")
        total_chars = sum(len(b.get("text", "")) for b in obs if b.get("type") == "text")
        print(f"total text chars: {total_chars}")

        client = LLMClient()
        from agent.tools.schema import TOOLS
        t0 = time.time()
        resp = await client.step(build_system_prompt(False), [{"role": "user", "content": obs}], TOOLS)
        print(f"LLM call took {time.time()-t0:.1f}s")
        print(resp.content)
    finally:
        await ctrl.close()


asyncio.run(main())
