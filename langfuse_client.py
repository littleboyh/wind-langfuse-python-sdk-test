"""Wind Langfuse client bootstrap shared by the Flask app and worker process.

The important convention in this file is: application code imports
`get_langfuse_client()` instead of constructing `WindLangfuse` directly.
That keeps Wind required fields, Langfuse credentials, sampling, and flush
settings consistent across files and across processes.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from dotenv import load_dotenv
from wind_langfuse import WindLangfuse


# Load `.env` once per process before any Wind/Langfuse client reads settings.
# The worker process imports this module too, so cross-process demos get the
# same credentials and Wind metadata without duplicating bootstrap code.
load_dotenv()


def _optional_int(name: str) -> int | None:
    value = os.getenv(name)
    return int(value) if value else None


def _optional_float(name: str) -> float | None:
    value = os.getenv(name)
    return float(value) if value else None


def _optional_bool(name: str) -> bool | None:
    value = os.getenv(name)
    if value is None:
        return None

    return value.lower() in {"1", "true", "yes", "on"}


def _set_if_present(kwargs: dict[str, Any], key: str, env_name: str) -> None:
    value = os.getenv(env_name)
    if value:
        kwargs[key] = value


@lru_cache(maxsize=1)
def get_langfuse_client() -> WindLangfuse:
    """Return one WindLangfuse client per Python process.

    Flask imports this function in the web process, while `worker.py` imports it
    in a separate Python process. Each process owns its own SDK queue, so both
    processes call `flush()` before returning/exiting.
    """

    langfuse_kwargs: dict[str, Any] = {}
    _set_if_present(langfuse_kwargs, "public_key", "LANGFUSE_PUBLIC_KEY")
    _set_if_present(langfuse_kwargs, "secret_key", "LANGFUSE_SECRET_KEY")
    _set_if_present(langfuse_kwargs, "base_url", "LANGFUSE_BASE_URL")

    timeout = _optional_int("LANGFUSE_TIMEOUT")
    flush_at = _optional_int("LANGFUSE_FLUSH_AT")
    flush_interval = _optional_int("LANGFUSE_FLUSH_INTERVAL")
    debug = _optional_bool("LANGFUSE_DEBUG")

    if timeout is not None:
        langfuse_kwargs["timeout"] = timeout
    if flush_at is not None:
        langfuse_kwargs["flush_at"] = flush_at
    if flush_interval is not None:
        langfuse_kwargs["flush_interval"] = flush_interval
    if debug is not None:
        langfuse_kwargs["debug"] = debug

    return WindLangfuse(
        product_name=os.getenv("WIND_PRODUCT_NAME", "demo"),
        app_name=os.getenv("WIND_APP_NAME", "flask-cross-process-demo"),
        app_class_id=os.getenv("WIND_APP_CLASS_ID", "wind-demo-app"),
        version=os.getenv("WIND_APP_VERSION", "0.1.0"),
        environment=os.getenv("WIND_APP_ENVIRONMENT", "dev"),
        sample_rate=_optional_float("LANGFUSE_SAMPLE_RATE"),
        **langfuse_kwargs,
    )


def flush_langfuse() -> None:
    """Flush buffered observations for the current process."""

    get_langfuse_client().flush()
