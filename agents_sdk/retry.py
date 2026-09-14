"""Shared retry/backoff logic for OpenAI API rate limits."""

from __future__ import annotations

import asyncio
import inspect
import logging
import re

from openai import RateLimitError

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
BASE_DELAY = 2  # seconds


def _parse_retry_after(error: RateLimitError) -> float | None:
    """Extract suggested wait time from the error message."""
    msg = str(error)
    match = re.search(r"try again in (\d+(?:\.\d+)?)s", msg, re.IGNORECASE)
    if match:
        return float(match.group(1))
    return None


async def run_with_retry(runner, *args, **kwargs) -> object:
    """Call Runner.run with exponential backoff on rate-limit errors.

    Retries up to MAX_RETRIES times, respecting the API's suggested
    retry-after delay when available.
    """
    for attempt in range(MAX_RETRIES + 1):
        try:
            result = runner.run(*args, **kwargs)
            if inspect.isawaitable(result):
                return await result
            return result
        except RateLimitError as exc:
            if attempt >= MAX_RETRIES:
                logger.error("Rate limit: max retries (%d) exceeded", MAX_RETRIES)
                raise
            retry_after = _parse_retry_after(exc)
            delay = retry_after if retry_after else BASE_DELAY * (2 ** attempt)
            logger.warning(
                "Rate limit hit (attempt %d/%d), retrying in %.1fs",
                attempt + 1,
                MAX_RETRIES,
                delay,
            )
            await asyncio.sleep(delay)

    # Should not reach here, but just in case
    raise RuntimeError("run_with_retry: exhausted retries")
