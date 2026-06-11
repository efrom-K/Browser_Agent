from agent.browser import actions
from agent.browser.perception import capture_state, format_elements

from .conftest import fixture_url


async def test_collects_visible_interactive_elements(controller):
    await controller.goto(fixture_url("simple_form.html"))
    state = await capture_state(controller.page)

    assert state.title == "Simple Form"
    assert len(state.elements) == 3  # input, button, link (hidden div excluded)

    by_tag = {el.tag: el for el in state.elements}
    assert by_tag["input"].name == "Search query"
    assert by_tag["button"].name == "Search"
    assert by_tag["a"].name == "External link"

    # Screenshot with marks should be a non-trivial PNG.
    assert state.screenshot[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(state.screenshot) > 1000


async def test_format_elements_is_readable(controller):
    await controller.goto(fixture_url("simple_form.html"))
    state = await capture_state(controller.page)

    text = format_elements(state.elements)
    lines = text.splitlines()

    assert len(lines) == 3
    assert all(line.startswith(f"[{i}]") for i, line in enumerate(lines))
    assert any('"Search"' in line for line in lines)


async def test_hidden_and_disabled_elements(controller):
    await controller.goto(fixture_url("buttons.html"))
    state = await capture_state(controller.page)

    names = {el.name for el in state.elements}
    # The hidden div is not an interactive element and is not collected at all.
    assert "I was hidden" not in names

    disabled = {el.name: el.disabled for el in state.elements}
    assert disabled["Disabled"] is True
    assert disabled["Count: 0"] is False


async def test_offscreen_elements_excluded(controller):
    await controller.goto(fixture_url("tall_page.html"))
    state = await capture_state(controller.page)

    # The button only becomes visible after scrolling.
    assert state.elements == []


async def test_capture_state_survives_navigation(controller):
    """Clicking a link can navigate the page while capture_state is reading
    it; capture_state should recover and describe the new page."""
    await controller.goto(fixture_url("link_page.html"))
    state = await capture_state(controller.page)

    link = next(el for el in state.elements if el.tag == "a")
    await actions.click(controller.page, link.id)

    new_state = await capture_state(controller.page)
    assert new_state.title == "Simple Form"
