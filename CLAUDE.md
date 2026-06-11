# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

An autonomous browser agent (Playwright + an Anthropic-Messages-API-compatible
LLM) that solves multi-step tasks by perceiving a page (numbered list of
interactive elements, optionally a screenshot), choosing one tool action per
turn, and re-evaluating after each action until it calls `finish_task` or
`ask_user`.

## Setup

Requires Python 3.13 (Python 3.14 is incompatible with Playwright's `greenlet`
dependency).

```powershell
py -3.13 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
playwright install chromium
```

Configure the LLM provider in `.env` (see `.env.example`). Default is z.ai's
free `glm-4.5-flash` via their Anthropic-compatible endpoint
(`ZAI_API_KEY`/`ZAI_BASE_URL`/`ZAI_MODEL`). To use the real Anthropic API
instead, set `ANTHROPIC_API_KEY`/`ANTHROPIC_MODEL` and `AGENT_VISION=true` -
no code changes needed (see `agent/config.py`).

## Common commands

```powershell
# Interactive agent: opens a visible Chromium window + terminal prompt for tasks
python scripts/run_agent.py

# Stage 0 sanity check - opens a visible Chromium window, screenshots example.com
python scripts/healthcheck.py

# Stage 1 demo - set-of-marks perception on a real page
python scripts/demo_perception.py

# Run the full test suite
pytest

# Run a single test file / test
pytest tests/integration/test_perception.py
pytest tests/integration/test_llm_step.py::test_agent_picks_search_input_for_search_task
```

Tests that call the LLM API are skipped automatically unless an API key is
configured (see `requires_api_key` marker in `tests/integration/test_llm_step.py`,
checks `config.LLM_API_KEY`).

`pytest.ini` sets `asyncio_mode = auto`, so async test functions don't need
`@pytest.mark.asyncio`.

## Architecture

The agent is built around a perceive -> decide -> act loop:

- **`agent/browser/controller.py`** - `BrowserController` owns the Playwright
  lifecycle (single browser + single page), used as an async context manager.
- **`agent/browser/perception.py`** + **`perception.js`** - "set-of-marks"
  perception: injects JS into the page to scan the live DOM for interactive
  elements, assigns each a numeric ID, draws red numbered boxes on a
  screenshot, and returns a `PageState` (url, title, `ElementInfo` list,
  screenshot bytes). Element IDs are only valid until the next page mutation -
  re-scan after every action. `capture_state` retries once if the action it's
  observing triggered a navigation that destroyed the JS execution context
  mid-scan.
- **`agent/browser/actions.py`** - executes actions (click, type_text, scroll,
  press_key) against elements by numeric ID, looked up via
  `window.__agentElements` set during the perception scan. Uses real mouse/
  keyboard events (not `element.click()`/`.value =`) so page JS listeners fire
  normally.
- **`agent/core/observation.py`** - `build_observation()`/`build_observation_content()`
  convert a `PageState` into content blocks (text description of visible
  elements, optionally + base64 screenshot via `include_screenshot`).
- **`agent/core/prompts.py`** - `build_system_prompt(vision: bool)` builds the
  system prompt: one tool call per turn, no upfront fixed plan, re-evaluate
  after every action, use `ask_user`/`finish_task`/`update_notes`. Vision and
  text-only modes get different perception instructions.
- **`agent/core/llm_client.py`** - `LLMClient.step()` is a thin async wrapper
  (via `asyncio.to_thread`) around `anthropic.Anthropic().messages.create`,
  using `config.LLM_API_KEY`/`LLM_BASE_URL`/`LLM_MODEL` (so any
  Anthropic-Messages-API-compatible provider works, not just Claude).
- **`agent/core/context.py`** - `trim_history()`: context management. Keeps
  only the most recent `config.CONTEXT_KEEP_LAST` tool-result observations in
  full (page description + screenshot); older ones are replaced with a short
  placeholder. Assistant messages (reasoning + actions taken) are never
  trimmed.
- **`agent/core/loop.py`** - `AgentLoop.run(task, on_step=...)`: the main
  perceive -> decide -> act loop. Handles `tool_use` dispatch, `ask_user`
  (pauses for a reply via an injectable async callback), `finish_task`
  (returns `AgentResult`), `update_notes` (agent-maintained scratchpad - see
  below), and `MAX_STEPS`. `on_step(StepEvent)` is called after every step for
  UI/logging.
- **`agent/tools/schema.py`** - `TOOLS`: the fixed, task-agnostic tool
  definitions exposed to the LLM (navigate, click, type_text, scroll,
  press_key, go_back, update_notes, ask_user, finish_task).
- **`agent/tools/dispatcher.py`** - `execute_tool()` maps a tool_use call to
  the corresponding `agent/browser/actions.py` call and returns a
  `ToolResult` (output text, plus `finished`/`success`/`ask_user_question`
  flags used by `AgentLoop`). Catches `ElementNotFoundError` and general
  Playwright errors so a single bad action returns an error message to the
  agent instead of crashing the loop.
- **`agent/config.py`** - loads `.env` via `python-dotenv`; provider settings
  (`LLM_API_KEY`/`LLM_BASE_URL`/`LLM_MODEL`), `VISION_ENABLED`, `MAX_STEPS`
  (`AGENT_MAX_STEPS`), `CONTEXT_KEEP_LAST` (`AGENT_CONTEXT_KEEP_LAST`).

### Working notes / scratchpad pattern

The `update_notes` tool lets the agent maintain a short free-text "working
memory" (plan, progress, facts discovered so far). `AgentLoop` stores this in
`self.notes` and appends it to the system prompt on every turn, so it survives
`trim_history()` removing detailed older observations - this is how the agent
keeps track of long multi-step tasks once early observations are trimmed.

### Vision vs. text-only perception

`AGENT_VISION` (`config.VISION_ENABLED`) controls whether screenshots are
captured/sent to the LLM. The free GLM models behind the z.ai endpoint don't
appear to use image input, so the default is text-only: the agent acts purely
on the element list from `perception.format_elements`. Set `AGENT_VISION=true`
for vision-capable models (e.g. Claude).

Tests in `tests/integration/` drive real (headless) browsers against local
HTML fixtures in `tests/fixtures/`.
