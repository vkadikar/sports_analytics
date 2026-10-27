"""
Thin, shared Gemini client setup for the league hub's LLM-backed features.

Loads credentials from soccer/config/.env (same file the Fantrax wrapper uses)
and hands back a configured `google.genai.Client`, retrying once or twice on
Gemini's transient 503 "high demand" responses, which are common.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable, Iterable, Iterator, TypeVar

from google import genai
from google.genai import errors as genai_errors
from google.genai.types import HttpOptions

from fantrax_wrapper import load_env_file

LLM_CLIENT_DIR = Path(__file__).resolve().parent
SOCCER_DIR = LLM_CLIENT_DIR.parent

# Gemini 2.5 models were retired for new API keys; this is the model Google's
# own API error pointed us to. Override with GEMINI_MODEL if that changes again.
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

T = TypeVar("T")

_client: genai.Client | None = None


def get_client() -> genai.Client:
    """Returns a lazily-created, process-wide Gemini client.

    Reads GEMINI_API_KEY (or GOOGLE_API_KEY) / the GOOGLE_GENAI_USE_VERTEXAI
    family of vars from soccer/config/.env on first call.
    """
    global _client
    if _client is None:
        load_env_file(str(SOCCER_DIR / "config" / ".env"))
        _client = genai.Client(http_options=HttpOptions(api_version="v1"))
    return _client


def stream_with_retry(make_stream: Callable[[], Iterable[T]], attempts: int = 3, delay_seconds: float = 4.0) -> Iterator[T]:
    """Yields from make_stream(), retrying on Gemini's transient 503 UNAVAILABLE ("high demand")
    errors. Only retries before the first chunk arrives; once chunks have been passed on, a
    restart would repeat them, so a later error is raised instead."""
    for attempt in range(attempts):
        started = False
        try:
            for chunk in make_stream():
                started = True
                yield chunk
            return
        except genai_errors.ServerError:
            if started or attempt == attempts - 1:
                raise
            time.sleep(delay_seconds)
