"""Thin wrapper around Playwright for launching and controlling a browser."""

from __future__ import annotations

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright


class BrowserController:
    """Owns the Playwright lifecycle and the single page the agent operates on."""

    def __init__(
        self,
        headless: bool = False,
        viewport: tuple[int, int] = (1280, 800),
        user_data_dir: str | None = None,
    ):
        self.headless = headless
        self.viewport = {"width": viewport[0], "height": viewport[1]}
        self.user_data_dir = user_data_dir
        self._playwright: Playwright | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        if self.user_data_dir:
            # Persistent context: keeps cookies/login state on disk across runs.
            self.context = await self._playwright.chromium.launch_persistent_context(
                self.user_data_dir, headless=self.headless, viewport=self.viewport
            )
            self.browser = self.context.browser
            self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        else:
            self.browser = await self._playwright.chromium.launch(headless=self.headless)
            self.page = await self.browser.new_page(viewport=self.viewport)

    async def goto(self, url: str) -> None:
        assert self.page is not None, "call start() first"
        await self.page.goto(url, wait_until="domcontentloaded")
        await wait_until_settled(self.page)

    async def close(self) -> None:
        if self.context:
            await self.context.close()
        elif self.browser:
            await self.browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def __aenter__(self) -> "BrowserController":
        await self.start()
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.close()


async def wait_until_settled(page: Page, timeout: int = 15000) -> None:
    """Give a page time to finish loading dynamic content after navigation.

    Many real sites (hh.ru, webmail, etc.) keep fetching/rendering content
    well after domcontentloaded; waiting for networkidle (with a generous
    timeout) avoids the agent perceiving a half-loaded page and giving up
    too early. Pages with long-polling/streaming connections never reach
    networkidle, so this is best-effort and falls through on timeout.
    """
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        pass
