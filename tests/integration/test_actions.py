from agent.browser import actions
from agent.browser.exceptions import ElementNotFoundError
from agent.browser.perception import capture_state

from .conftest import fixture_url


async def test_click_increments_counter(controller):
    await controller.goto(fixture_url("buttons.html"))
    state = await capture_state(controller.page)

    counter = next(el for el in state.elements if el.name == "Count: 0")
    await actions.click(controller.page, counter.id)

    text = await controller.page.text_content("#counter")
    assert text == "Count: 1"


async def test_type_and_submit_search(controller):
    await controller.goto(fixture_url("simple_form.html"))
    state = await capture_state(controller.page)

    input_el = next(el for el in state.elements if el.tag == "input")
    button_el = next(el for el in state.elements if el.tag == "button")

    await actions.type_text(controller.page, input_el.id, "playwright")
    await actions.click(controller.page, button_el.id)

    result = await controller.page.text_content("#result")
    assert result == "Results for: playwright"


async def test_scroll_reveals_new_elements(controller):
    await controller.goto(fixture_url("tall_page.html"))
    state = await capture_state(controller.page)
    assert state.elements == []

    await actions.scroll(controller.page, "down", amount=2200)
    state_after = await capture_state(controller.page)

    assert len(state_after.elements) == 1
    assert state_after.elements[0].name == "Bottom button"


async def test_unknown_element_id_raises(controller):
    await controller.goto(fixture_url("simple_form.html"))
    await capture_state(controller.page)

    try:
        await actions.click(controller.page, 999)
        assert False, "expected ElementNotFoundError"
    except ElementNotFoundError as exc:
        assert exc.element_id == 999
