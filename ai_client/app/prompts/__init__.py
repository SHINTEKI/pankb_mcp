"""Prompt registry — every version stays in git forever.

To add a new version:
  1. Copy prompts/vN.py to prompts/v{N+1}.py and edit.
  2. Add it to PROMPTS below.
  3. Set PROMPT_VERSION in .env to switch (DEFAULT_VERSION is only a fallback).

Resolution order: PROMPT_VERSION env > DEFAULT_VERSION (with a logged warning).
"""
import logging
import os

from . import v1

logger = logging.getLogger(__name__)

DEFAULT_VERSION = "v1"

PROMPTS = {
    "v1": v1.SYSTEM_PROMPT,
}


def get_prompt() -> tuple[str, str]:
    """Return (resolved_version, prompt_text).

    The resolved version is also what gets stamped on agent.chat spans, so
    Phoenix always shows what *actually* ran — not what was requested.
    """
    requested = os.getenv("PROMPT_VERSION") or ""
    if requested in PROMPTS:
        return requested, PROMPTS[requested]

    if not requested:
        logger.warning(
            "PROMPT_VERSION env not set — falling back to DEFAULT_VERSION=%r",
            DEFAULT_VERSION,
        )
    else:
        logger.warning(
            "PROMPT_VERSION=%r is not registered (available: %s) — "
            "falling back to DEFAULT_VERSION=%r",
            requested, sorted(PROMPTS), DEFAULT_VERSION,
        )
    return DEFAULT_VERSION, PROMPTS[DEFAULT_VERSION]
