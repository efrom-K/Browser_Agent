"""Centralized configuration loaded from environment variables / .env file."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# LLM provider settings. Provider is picked by which API key is set, in
# order of preference: real Anthropic API > OpenRouter (Anthropic-compatible
# endpoint, any model) > z.ai (free GLM models). All three speak the
# Anthropic Messages API, so no code changes are needed to switch.
if os.environ.get("ANTHROPIC_API_KEY"):
    LLM_API_KEY = os.environ["ANTHROPIC_API_KEY"]
    LLM_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL") or None
    LLM_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
elif os.environ.get("OPENROUTER_API_KEY"):
    LLM_API_KEY = os.environ["OPENROUTER_API_KEY"]
    LLM_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api")
    LLM_MODEL = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-haiku-4.5")
else:
    LLM_API_KEY = os.environ.get("ZAI_API_KEY", "")
    LLM_BASE_URL = os.environ.get("ZAI_BASE_URL") or None
    LLM_MODEL = os.environ.get("ZAI_MODEL", "glm-4.5-flash")

# Whether to send screenshots to the LLM. The free GLM models behind the
# z.ai endpoint do not appear to process image content, so this defaults to
# off; set AGENT_VISION=true when using a vision-capable model (e.g. Claude).
VISION_ENABLED = os.environ.get("AGENT_VISION", "false").lower() == "true"

# Per-request timeout (seconds) for LLM API calls, so a hung provider
# request doesn't stall the whole agent loop indefinitely.
LLM_TIMEOUT = float(os.environ.get("AGENT_LLM_TIMEOUT", "60"))

# Safety limits for the autonomous loop (used from Stage 3 onwards).
MAX_STEPS = int(os.environ.get("AGENT_MAX_STEPS", "50"))

# Context management: number of most recent tool-result observations (page
# description + screenshot) to keep in full. Older observations are
# replaced with a short placeholder to keep the conversation from growing
# without bound on long tasks.
CONTEXT_KEEP_LAST = int(os.environ.get("AGENT_CONTEXT_KEEP_LAST", "3"))
