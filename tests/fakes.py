"""Test doubles and builders shared by the pattern and doc_rag tests."""

from __future__ import annotations

from typing import Any

from jev_agent.jev import JevResult


class ScriptedJev:
    """Answers each question from a {name: answer} script and records what it was asked."""

    def __init__(self, answers: dict[str, dict[str, Any]], default: dict[str, Any] | None = None):
        self.answers = answers
        self.default = default
        self.calls: list[tuple[Any, dict]] = []

    def decide(self, state: Any, questions: dict) -> JevResult:
        self.calls.append((state, questions))
        answers = {name: self.answers.get(name, self.default) for name in questions}
        return JevResult(answers=answers, usage={"cost": 0.00001}, latency_ms=10.0)

    async def adecide(self, state: Any, questions: dict) -> JevResult:
        return self.decide(state, questions)


def doc(title: str, summary: str, *paragraphs: str) -> str:
    """A document in the corpus format: title, summary paragraph, then body paragraphs."""
    return "\n\n".join([f"# {title}", summary, *paragraphs]) + "\n"
