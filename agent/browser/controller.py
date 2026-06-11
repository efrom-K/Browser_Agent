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
        try:
            await self.page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            # Pages with long-polling/streaming connections never reach
            # networkidle; domcontentloaded is good enough to proceed.
            pass

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
