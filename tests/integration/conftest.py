from pathlib import Path

import pytest

from agent.browser.controller import BrowserController

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture
async def controller():
    ctrl = BrowserController(headless=True)
    await ctrl.start()
    try:
        yield ctrl
    finally:
        await ctrl.close()


def fixture_url(name: str) -> str:
    return (FIXTURES_DIR / name).as_uri()
