"""Stage 0 sanity check: launch a headed browser, open a page, take a screenshot.

Run with:
    python scripts/healthcheck.py

A visible Chromium window should appear, navigate to example.com, and a
screenshot will be saved to ./runs/healthcheck.png.
"""

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

RUNS_DIR = Path(__file__).resolve().parent.parent / "runs"


async def main() -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=["--start-maximized"])
        page = await browser.new_page(viewport=None)
        await page.goto("https://example.com")
        await page.wait_for_load_state("networkidle")
        screenshot_path = RUNS_DIR / "healthcheck.png"
        await page.screenshot(path=str(screenshot_path))
        print(f"Screenshot saved to {screenshot_path}")

        print("Browser window is open. Closing in 10 seconds...")
        await asyncio.sleep(10)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
