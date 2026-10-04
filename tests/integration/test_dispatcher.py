from agent.browser.perception import capture_state
from agent.tools.dispatcher import execute_tool

from .conftest import fixture_url


async def test_navigate_error_is_returned_not_raised(controller):
    await controller.goto(fixture_url("simple_form.html"))

    result = await execute_tool(controller.page, "navigate", {"url": "not-a-valid-url"})

    assert result.finished is False
    assert result.output.startswith("Error:")


async def test_finish_task_marks_finished():
    result = await execute_tool(None, "finish_task", {"summary": "All done", "success": True})

    assert result.finished is True
    assert result.success is True
    assert result.output == "All done"


async def test_read_page_text_returns_full_body_text(controller):
    await controller.goto(fixture_url("article.html"))

    result = await execute_tool(controller.page, "read_page_text", {})

    assert "Playwright is a framework" in result.output
    assert "About Playwright" in result.output


async def test_read_page_text_for_specific_element(controller):
    await controller.goto(fixture_url("article.html"))
    await capture_state(controller.page, mark_screenshot=False)

    state = await capture_state(controller.page, mark_screenshot=False)
    link = next(el for el in state.elements if el.tag == "a")

    result = await execute_tool(controller.page, "read_page_text", {"element_id": link.id})

    assert "Open form in new tab" in result.output
    assert "Playwright is a framework" not in result.output


async def test_click_target_blank_link_opens_new_tab(controller):
    await controller.goto(fixture_url("article.html"))
    state = await capture_state(controller.page, mark_screenshot=False)
    link = next(el for el in state.elements if el.tag == "a")

    result = await execute_tool(controller.page, "click", {"element_id": link.id})

    assert result.new_page is not None
    assert "simple_form.html" in result.new_page.url
    assert len(controller.page.context.pages) == 2

    close_result = await execute_tool(result.new_page, "close_tab", {})
    assert close_result.new_page is controller.page
    assert len(controller.page.context.pages) == 1


async def test_close_tab_with_only_one_tab_open(controller):
    await controller.goto(fixture_url("article.html"))

    result = await execute_tool(controller.page, "close_tab", {})

    assert result.output.startswith("Error:")


async def test_read_page_text_continues_on_repeat(controller):
    words = " ".join(f"w{i}" for i in range(2000))  # ~10k chars -> 3 chunks
    await controller.page.set_content(f"<p>{words}</p>")
    page = controller.page

    first = (await execute_tool(page, "read_page_text", {})).output
    second = (await execute_tool(page, "read_page_text", {})).output
    third = (await execute_tool(page, "read_page_text", {})).output
    again = (await execute_tool(page, "read_page_text", {})).output

    assert first.startswith("w0 ") and "call read_page_text again" in first
    assert not second.startswith("w0 ") and "chars 4000-8000" in second
    assert "(end of page text)" in third
    assert again.startswith("w0 ")  # after the end, starts over


async def test_read_list_returns_compact_items(controller):
    cards = "".join(
        f'<div class="card"><p><a href="/item/{i}?ref=x">Phone {i}</a></p><p>{1000 + i} ₽</p>'
        f'<p><button>Write</button></p></div>'
        for i in range(30)
    )
    await controller.page.set_content(f'<div class="list">{cards}</div><a href="/about">About us page</a>')

    first = (await execute_tool(controller.page, "read_list", {})).output
    second = (await execute_tool(controller.page, "read_list", {})).output

    assert "List of 30 items" in first and "#1 Phone 0 | 1000 ₽ -> /item/0" in first
    assert "Write" not in first and "#26 " not in first
    assert "#26 Phone 25" in second and "end of list" in second


async def test_navigate_to_current_page_does_not_reload(controller):
    await controller.goto(fixture_url("buttons.html"))
    await controller.page.evaluate("window.__marker = 1")

    result = await execute_tool(controller.page, "navigate", {"url": fixture_url("buttons.html")})

    assert result.output.startswith("Already on")
    assert await controller.page.evaluate("window.__marker") == 1
