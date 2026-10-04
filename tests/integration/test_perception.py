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


async def test_captcha_flag_on_block_page_but_not_on_content_mentioning_it(controller):
    await controller.page.set_content(
        "<h1>Доступ ограничен: проблема с IP</h1><p>Нажмите «Продолжить» для решения капчи</p><button>Продолжить</button>"
    )
    assert (await capture_state(controller.page, mark_screenshot=False)).captcha

    results = "".join(f"<p><a href='/r/{i}'>Repo {i}: playwright tool that is undetected by captchas</a> {'x' * 80}</p>" for i in range(30))
    await controller.page.set_content(f"<title>Search results</title>{results}")
    assert not (await capture_state(controller.page, mark_screenshot=False)).captcha


async def test_offscreen_next_page_link_is_listed(controller):
    await controller.page.set_content(
        "<a href='/a'>Top link</a><div style='height:5000px'></div><a href='/list?p=2'>Next ›</a>"
    )
    state = await capture_state(controller.page, mark_screenshot=False)

    lines = format_elements(state.elements).splitlines()
    assert any("Next ›" in line and "(next page)" in line and "/list?p=2" in line for line in lines)


async def test_captcha_flag_ignores_title_of_long_content_page(controller):
    body = "".join(f"<p>Paragraph {i} about browser automation and testing tools.</p>" for i in range(60))
    await controller.page.set_content(f"<title>repo: MCP server undetected by anti-bots and captchas</title>{body}")
    assert not (await capture_state(controller.page, mark_screenshot=False)).captcha
