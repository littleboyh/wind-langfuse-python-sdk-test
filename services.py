"""Small demo business functions used by both processes."""

from __future__ import annotations


def normalize_text(text: str) -> str:
    """Keep the business logic boring so the tracing structure is easy to see."""

    return " ".join(text.strip().split())


def fake_llm_answer(text: str) -> str:
    """Pretend this is an LLM result without requiring an external model call."""

    return f"demo-answer: {text[::-1]}"
