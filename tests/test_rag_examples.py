"""The example chips in the RAG tab are a hand copy of the server's sample queries; keep them equal."""

from __future__ import annotations

from pathlib import Path

import pytest

from jev_agent.rag.corpus import SAMPLE_QUERIES

RAG_TAB = Path(__file__).resolve().parent.parent / "frontend" / "src" / "rag" / "RagTab.tsx"


@pytest.mark.parametrize("sample", SAMPLE_QUERIES, ids=[s["label"] for s in SAMPLE_QUERIES])
def test_rag_tab_examples_contain_every_server_sample_query(sample):
    tab_source = RAG_TAB.read_text(encoding="utf-8")

    assert sample["query"] in tab_source
