"""Tool definitions exposed to Claude.

These are the only actions the agent can take. There is nothing
task-specific here: the agent decides which tool to call, on which
element_id, based on what it currently sees on the screen.
"""

TOOLS = [
    {
        "name": "navigate",
        "description": (
            "Navigate the browser to an absolute URL. Use this to open a new "
            "site or to go to a URL you already know (e.g. from a link's "
            "destination)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Absolute URL to open."},
            },
            "required": ["url"],
        },
    },
    {
        "name": "click",
        "description": (
            "Click an interactive element. Reference it by the numeric ID "
            "shown for it in the current observation (element list, and red "
            "label in the screenshot if vision is enabled)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "element_id": {
                    "type": "integer",
                    "description": "The numeric ID label shown on the element in the screenshot.",
                },
            },
            "required": ["element_id"],
        },
    },
    {
        "name": "type_text",
        "description": (
            "Click an input/textarea/contenteditable element (identified by its "
            "numeric ID), clear any existing value, and type the given text. "
            "Optionally press Enter afterwards to submit."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "element_id": {
                    "type": "integer",
                    "description": "The numeric ID shown for the element in the current observation.",
                },
                "text": {"type": "string", "description": "Text to type into the element."},
                "submit": {
                    "type": "boolean",
                    "description": "If true, press Enter after typing to submit.",
                    "default": False,
                },
            },
            "required": ["element_id", "text"],
        },
    },
    {
        "name": "scroll",
        "description": "Scroll the page up or down to reveal more content/elements.",
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {"type": "string", "enum": ["up", "down"]},
                "amount": {
                    "type": "integer",
                    "description": "Approximate number of pixels to scroll. Defaults to 600.",
                    "default": 600,
                },
            },
            "required": ["direction"],
        },
    },
    {
        "name": "press_key",
        "description": (
            "Press a single keyboard key on the currently focused element, e.g. "
            "'Enter', 'Escape', 'Tab', 'ArrowDown'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Key name, as understood by Playwright (e.g. 'Enter')."},
            },
            "required": ["key"],
        },
    },
    {
        "name": "go_back",
        "description": "Navigate back to the previous page in browser history.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "read_list",
        "description": (
            "Read the main list of repeated items on the current page (search "
            "results, listings, products, vacancies...) compactly: one line per "
            "item with its key facts (title, price, attributes, seller/rating) "
            "and its link. Much faster than read_page_text for comparing many "
            "items. Returns 25 items per call; call again for the next ones."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "pick_items",
        "description": (
            "Choose items from the current page's read_list output by their "
            "numbers (e.g. the best candidates for the task). The exact item "
            "details and links are saved for you and included in your final "
            "answer automatically - don't copy them into notes or the summary. "
            "Picks accumulate across pages."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "item_numbers": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "The #numbers that start the read_list lines on this page (e.g. 3 for '#3 ...').",
                },
            },
            "required": ["item_numbers"],
        },
    },
    {
        "name": "read_page_text",
        "description": (
            "Read the visible text content of the current page (or, if "
            "element_id is given, of just that element and its children). "
            "Use this to read long text that isn't part of the interactive "
            "element list, such as articles, job/product descriptions, "
            "profile or resume content, or terms of service. Long text is "
            "returned in 4000-character chunks; calling it again on the same "
            "page continues with the next chunk."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "element_id": {
                    "type": "integer",
                    "description": "Optional: read only this element's text instead of the whole page.",
                },
                "offset": {
                    "type": "integer",
                    "description": "Optional: character offset to start from, to continue reading a truncated text.",
                },
            },
        },
    },
    {
        "name": "close_tab",
        "description": (
            "Close the current browser tab and switch back to the previous "
            "tab. Clicking some links opens their target in a new tab "
            "(you'll automatically switch to it); use this to return to the "
            "page you came from once you're done with the new tab."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "update_notes",
        "description": (
            "Replace your working notes with the given text. Use this to track "
            "your plan, progress so far, and important facts you've found "
            "(e.g. values you've entered, items you've selected, results "
            "you've seen) - on long tasks, detailed older observations are "
            "removed from your context to save space, but these notes are "
            "always shown to you. Keep it short and up to date; each call "
            "replaces the previous notes entirely."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "notes": {"type": "string"},
            },
            "required": ["notes"],
        },
    },
    {
        "name": "ask_user",
        "description": (
            "Pause and ask the human user a question, e.g. when you need "
            "credentials, a decision, or information that isn't available on "
            "the page. Execution stops until the user replies."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
            },
            "required": ["question"],
        },
    },
    {
        "name": "finish_task",
        "description": (
            "Call this when the task is complete (or cannot be completed). "
            "Provide a summary of what was done and the final result. If you "
            "chose items with pick_items, they are appended to the summary "
            "automatically - then keep the summary to a few sentences (e.g. "
            "the criteria you used) and don't list the items again."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "success": {"type": "boolean"},
            },
            "required": ["summary", "success"],
        },
    },
]
