"""Worker process for the cross-process Wind Langfuse demo.

The Flask process passes `trace_id` and `parent_span_id` on the command line.
The worker then starts observations with `trace_context`, so its spans and
generations are attached to the same Langfuse trace as the HTTP request.
"""

from __future__ import annotations

import argparse
import json
import sys

from langfuse_client import flush_langfuse, get_langfuse_client
from services import fake_llm_answer, normalize_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run demo work in another process.")
    parser.add_argument("--trace-id", required=True, help="Langfuse trace id from Flask.")
    parser.add_argument(
        "--parent-span-id",
        required=True,
        help="Parent observation id from Flask, used to link process boundaries.",
    )
    parser.add_argument("--request-id", required=True, help="HTTP request id.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = json.load(sys.stdin)
    client = get_langfuse_client()

    trace_context = {
        "trace_id": args.trace_id,
        "parent_span_id": args.parent_span_id,
    }

    with client.start_as_current_span(
        name="worker.process",
        trace_context=trace_context,
        input={"request_id": args.request_id, "payload": payload},
        metadata={"process": "worker"},
    ) as span:
        text = normalize_text(payload.get("text", ""))

        with span.start_as_current_span(
            name="worker.normalize",
            input={"text": payload.get("text", "")},
        ) as normalize_span:
            normalize_span.update(output={"text": text})

        with span.start_as_current_generation(
            name="worker.fake-generation",
            model="demo-reverse-string",
            input={"prompt": text},
        ) as generation:
            answer = fake_llm_answer(text)
            generation.update(
                output=answer,
                usage_details={
                    "prompt_tokens": len(text.split()),
                    "completion_tokens": len(answer.split()),
                },
            )

        span.create_event(
            name="worker.finished",
            metadata={"request_id": args.request_id, "text_length": len(text)},
        )
        span.update(output={"answer": answer, "normalized_text": text})

    flush_langfuse()
    json.dump({"answer": answer, "normalized_text": text}, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
