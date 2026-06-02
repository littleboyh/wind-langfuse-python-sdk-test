"""Flask entry point for the Wind Langfuse cross-process demo."""

from __future__ import annotations

import atexit
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

from flask import Flask, jsonify, request

from langfuse_client import flush_langfuse, get_langfuse_client

app = Flask(__name__)
PROJECT_DIR = Path(__file__).resolve().parent
WORKER_PATH = PROJECT_DIR / "worker.py"


def _observation_id(observation: object) -> str:
    """Get the underlying Langfuse observation id in a wrapper-tolerant way."""

    value = getattr(observation, "id", None) or getattr(observation, "observation_id", None)
    if value is None:
        raise RuntimeError("Cannot read current observation id for trace propagation.")

    return str(value)


def _run_worker(*, trace_id: str, parent_span_id: str, request_id: str, payload: dict) -> dict:
    """Call another Python process and return its JSON result."""

    completed = subprocess.run(
        [
            sys.executable,
            str(WORKER_PATH),
            "--trace-id",
            trace_id,
            "--parent-span-id",
            parent_span_id,
            "--request-id",
            request_id,
        ],
        cwd=PROJECT_DIR,
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        timeout=20,
        check=True,
    )
    return json.loads(completed.stdout)


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/demo")
def demo():
    client = get_langfuse_client()
    payload = request.get_json(silent=True) or {}
    request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))

    with client.start_as_current_span(
        name="http.demo",
        input={"request_id": request_id, "payload": payload},
        metadata={"framework": "flask", "process": "web"},
    ) as span:
        # Wind wrapper intentionally drops `name` here, but forwards other trace fields.
        span.update_trace(
            name="ignored-by-wind-wrapper",
            user_id=payload.get("user_id", "anonymous"),
            session_id=payload.get("session_id", request_id),
            tags=["flask", "cross-process", os.getenv("WIND_APP_ENVIRONMENT", "dev")],
            metadata={"request_id": request_id, "entrypoint": "POST /demo"},
        )

        client.create_event(
            name="request.accepted",
            metadata={"request_id": request_id, "content_type": request.content_type},
        )

        worker_result = _run_worker(
            trace_id=span.trace_id,
            parent_span_id=_observation_id(span),
            request_id=request_id,
            payload=payload,
        )

        trace_id = span.trace_id
        trace_url = client.native_client.get_trace_url(trace_id=trace_id)
        span.update(output={"request_id": request_id, "worker": worker_result})

    # Web process and worker process have separate queues; both flush their own data.
    flush_langfuse()
    return jsonify(
        {
            "request_id": request_id,
            "trace_id": trace_id,
            "trace_url": trace_url,
            **worker_result,
        }
    )


@app.get("/trace-url/<trace_id>")
def trace_url(trace_id: str):
    """Tiny example of accessing native Langfuse APIs through the wrapper."""

    client = get_langfuse_client()
    return jsonify(
        {"trace_id": trace_id, "url": client.native_client.get_trace_url(trace_id=trace_id)}
    )


atexit.register(flush_langfuse)


if __name__ == "__main__":
    app.run(
        host=os.getenv("FLASK_HOST", "127.0.0.1"),
        port=int(os.getenv("FLASK_PORT", "5000")),
        debug=False,
        use_reloader=False,
    )
