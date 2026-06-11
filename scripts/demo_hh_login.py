"""One-time helper: opens hh.ru in a visible browser using a persistent
profile so you can log in manually. Cookies/session are saved to
`.hh_profile/` and reused by `scripts/demo_hh.py`.

Run with:
    python scripts/demo_hh_login.py

Log in to hh.ru in the window that opens, then close the browser window to
finish.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from agent.browser.controller import BrowserController

PROFILE_DIR = Path(__file__).resolve().parent.parent / ".hh_profile"


async def main() -> None:
    print(f"Using profile dir: {PROFILE_DIR}")
    ctrl = BrowserController(headless=False, user_data_dir=str(PROFILE_DIR))
    await ctrl.start()
    await ctrl.page.goto("https://hh.ru/account/login", wait_until="domcontentloaded")
    print("Log in to hh.ru in the opened browser window.")
    print("When you're done, close the browser window to continue.")
    try:
        await ctrl.page.wait_for_event("close", timeout=0)
    except Exception:
        pass
    await ctrl.close()
    print("Session saved. You can now run scripts/demo_hh.py")


if __name__ == "__main__":
    asyncio.run(main())
