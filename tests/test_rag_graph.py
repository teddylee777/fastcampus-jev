"""Unit tests for the doc_rag decisions and graph. A scripted Jev and a fake LLM are used; no network."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

import jev_agent.rag.graph as rag_graph
from jev_agent.jev import JevError, JevResult
from jev_agent.rag.corpus import CorpusIndex
from jev_agent.rag.decisions import (
    FILE_THRESHOLD,
    FOLDER_THRESHOLD,
    MAX_FILES,
    MAX_FOLDERS,
    MAX_PASSAGE_CHARS,
    NONE_OPTION,
    REFUSAL_ANSWER,
    SUFFICIENCY_THRESHOLD,
    build_file_question,
    build_folder_question,
    build_step,
    format_passages,
    is_refusal,
    read_answer,
    read_grounding,
    read_noul,
    read_probabilities,
    select_labels,
)
from jev_agent.rag.graph import ANSWER_SYSTEM_PROMPT, build_doc_rag_graph

REPO_ROOT = Path(__file__).resolve().parent.parent
ANSWER_TEXT = "배송비는 3천 원입니다."


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


class FailingJev(ScriptedJev):
    """Raises JevError on the fail_on-th adecide call (1-based)."""

    def __init__(self, answers: dict[str, dict[str, Any]], fail_on: int):
        super().__init__(answers)
        self.fail_on = fail_on

    async def adecide(self, state: Any, questions: dict) -> JevResult:
        if len(self.calls) + 1 == self.fail_on:
            self.calls.append((state, questions))
            raise JevError("Jev 호출 실패 (HTTP 402)")
        return self.decide(state, questions)


class ListAnswersJev(ScriptedJev):
    """Returns an `answers` that is not a mapping."""

    async def adecide(self, state: Any, questions: dict) -> JevResult:
        self.calls.append((state, questions))
        return JevResult(answers=[], usage={"cost": 0.00001}, latency_ms=10.0)


class UsageJev(ScriptedJev):
    """Answers as scripted but reports the given `usage` verbatim."""

    def __init__(self, answers: dict[str, dict[str, Any]], usage: Any):
        super().__init__(answers)
        self.usage = usage

    def decide(self, state: Any, questions: dict) -> JevResult:
        self.calls.append((state, questions))
        answers = {name: self.answers.get(name) for name in questions}
        return JevResult(answers=answers, usage=self.usage, latency_ms=10.0)


class FakeAnswerLLM:
    """Stands in for the chat model that writes the answer; records the messages it receives."""

    def __init__(self, content: Any = ANSWER_TEXT, fail: bool = False):
        self.content = content
        self.fail = fail
        self.calls: list[list[tuple[str, str]]] = []

    async def ainvoke(self, messages: list[tuple[str, str]]) -> AIMessage:
        self.calls.append(messages)
        if self.fail:
            raise RuntimeError("secret detail")
        return AIMessage(content=self.content)


def choice_answer(probabilities: dict[str, float]) -> dict[str, Any]:
    top = max(probabilities, key=lambda key: probabilities[key])
    return {
        "type": "choice",
        "choice": top,
        "confidence": probabilities[top],
        "probabilities": probabilities,
    }


def noul_answer(probability: float) -> dict[str, Any]:
    return {"type": "noul", "noul": probability}


def grounding_answer(label: str = "supports") -> dict[str, Any]:
    probabilities = {"contradicts": 0.1, "says_nothing": 0.1, "supports": 0.1}
    probabilities[label] = 0.8
    return choice_answer(probabilities)


def happy_answers() -> dict[str, dict[str, Any]]:
    """One script for all four Jev calls; the question names are distinct."""
    return {
        "folder": choice_answer({"shipping": 0.9, "returns": 0.05, NONE_OPTION: 0.05}),
        "file": choice_answer(
            {"shipping__delivery_fee": 0.8, "shipping__delivery_time": 0.1, NONE_OPTION: 0.1}
        ),
        "sufficient": noul_answer(0.9),
        "grounding": grounding_answer(),
    }


def doc(title: str, summary: str, *paragraphs: str) -> str:
    return "\n\n".join([f"# {title}", summary, *paragraphs]) + "\n"


@pytest.fixture
def corpus_root(tmp_path: Path) -> Path:
    """Two folders, three documents."""
    layout = {
        "shipping": {
            "_folder.md": "배송 안내",
            "delivery_fee.md": doc(
                "배송비 안내", "배송비 기준입니다.", "기본 배송비는 3천 원입니다."
            ),
            "delivery_time.md": doc("배송 기간", "배송 기간입니다.", "배송은 2일 걸립니다."),
        },
        "returns": {
            "_folder.md": "환불 안내",
            "refund_policy.md": doc(
                "환불 규정", "환불 규정입니다.", "환불은 7일 안에 신청합니다."
            ),
        },
    }
    for folder, files in layout.items():
        (tmp_path / folder).mkdir()
        for name, content in files.items():
            (tmp_path / folder / name).write_text(content, encoding="utf-8")
    return tmp_path


def run_graph(graph, payload: Any, config: dict | None = None) -> dict[str, Any]:
    return asyncio.run(graph.ainvoke({"payload": payload}, config))


def build_graph(corpus_root: Path, jev: ScriptedJev, llm: FakeAnswerLLM, **kwargs):
    return build_doc_rag_graph(jev=jev, llm=llm, root=corpus_root, **kwargs)


# --- select_labels ----------------------------------------------------------------
@pytest.mark.parametrize(
    ("threshold", "limit"), [(FOLDER_THRESHOLD, MAX_FOLDERS), (FILE_THRESHOLD, MAX_FILES)]
)
def test_select_labels_keeps_options_at_or_above_threshold(threshold, limit):
    probabilities = {"at": threshold, "below": threshold - 0.01, NONE_OPTION: 0.0}

    assert select_labels(probabilities, threshold, limit) == ["at"]


@pytest.mark.parametrize(
    "probabilities",
    [
        {NONE_OPTION: 0.45, "shipping": 0.30},
        {NONE_OPTION: 0.30, "shipping": 0.30},
    ],
    ids=["none_on_top", "none_tied_for_top"],
)
def test_select_labels_none_on_top_or_tied_returns_empty(probabilities):
    assert select_labels(probabilities, FOLDER_THRESHOLD, MAX_FOLDERS) == []


def test_select_labels_caps_at_limit():
    probabilities = {
        "a": FOLDER_THRESHOLD + 0.3,
        "b": FOLDER_THRESHOLD + 0.2,
        "c": FOLDER_THRESHOLD + 0.1,
        NONE_OPTION: 0.0,
    }

    assert select_labels(probabilities, FOLDER_THRESHOLD, MAX_FOLDERS) == ["a", "b"]


def test_select_labels_ignores_option_order():
    forward = {"a": 0.4, "b": 0.4, "c": 0.3, NONE_OPTION: 0.1}
    backward = dict(reversed(list(forward.items())))

    assert select_labels(forward, FOLDER_THRESHOLD, 3) == select_labels(
        backward, FOLDER_THRESHOLD, 3
    )
    assert select_labels(forward, FOLDER_THRESHOLD, 3) == ["a", "b", "c"]


# --- questions --------------------------------------------------------------------
def make_index(folders: list[str], files: list[tuple[str, str]]) -> CorpusIndex:
    return {
        "root": "unused",
        "folders": [{"name": name, "description": f"{name} 설명"} for name in folders],
        "files": [
            {
                "key": f"{folder}__{stem}",
                "path": f"{folder}/{stem}.md",
                "folder": folder,
                "title": f"{stem} 제목",
                "summary": f"{stem} 요약",
            }
            for folder, stem in files
        ],
    }


@pytest.mark.parametrize("reverse", [False, True], ids=["name_order", "reverse_order"])
def test_build_questions_order_options_by_name_with_none_last(reverse):
    folders = ["returns", "shipping"]
    files = [("returns", "refund"), ("shipping", "fee"), ("shipping", "time")]
    index = make_index(folders[::-1] if reverse else folders, files[::-1] if reverse else files)

    folder_state, folder_questions = build_folder_question(index, "질의")
    file_state, file_questions = build_file_question(index, ["shipping", "returns"], "질의")

    assert folder_state == {"query": "질의"}
    assert list(folder_questions["folder"]["criteria"]) == ["returns", "shipping", NONE_OPTION]
    assert file_state == {"query": "질의"}
    assert list(file_questions["file"]["criteria"]) == [
        "returns__refund",
        "shipping__fee",
        "shipping__time",
        NONE_OPTION,
    ]
    assert file_questions["file"]["criteria"]["shipping__fee"] == "fee 제목: fee 요약"


# --- readers ----------------------------------------------------------------------
@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        (
            {"probabilities": {"a": 0.7, "ghost": 0.9, NONE_OPTION: 0.3}},
            {"a": 0.7, NONE_OPTION: 0.3},
        ),
        ({"probabilities": {"a": 0.7, "ghost": "not-a-number"}}, {"a": 0.7}),
        ({"choice": "a"}, {"a": 1.0}),
        ({"probabilities": {"ghost": 1.0}, "choice": "a"}, {"a": 1.0}),
    ],
    ids=[
        "drops_unknown_key",
        "drops_unknown_key_with_bad_value",
        "choice_only",
        "only_unknown_keys",
    ],
)
def test_read_probabilities_drops_unknown_keys_and_falls_back_to_choice(answer, expected):
    assert read_probabilities(answer, ["a", NONE_OPTION]) == expected


@pytest.mark.parametrize(
    "answer",
    [
        None,
        {},
        {"choice": "ghost"},
        {"probabilities": ["a"]},
        {"probabilities": None},
        {"probabilities": {"a": True}},
        {"probabilities": {"a": "0.5"}},
        {"probabilities": {"a": 1.2}},
        {"probabilities": {"a": -0.1}},
    ],
)
def test_read_probabilities_rejects_malformed_answer(answer):
    with pytest.raises(ValueError):
        read_probabilities(answer, ["a", NONE_OPTION])


@pytest.mark.parametrize(
    "answer",
    [None, {"type": "noul"}, {"noul": "0.5"}, {"noul": True}, {"noul": 1.5}, {"noul": -0.1}],
)
def test_read_noul_rejects_malformed_answer(answer):
    with pytest.raises(ValueError):
        read_noul(answer)


def test_read_noul_returns_probability_as_float():
    assert read_noul({"noul": 1}) == 1.0
    assert read_noul({"noul": 0.25}) == 0.25


@pytest.mark.parametrize("answers", [None, []], ids=["none", "list"])
def test_read_answer_rejects_non_mapping_answers(answers):
    with pytest.raises(ValueError):
        read_answer(JevResult(answers=answers), "folder")


def test_read_answer_returns_named_answer_or_none_for_missing_name():
    result = JevResult(answers={"folder": {"choice": "a"}})

    assert read_answer(result, "folder") == {"choice": "a"}
    assert read_answer(result, "file") is None


@pytest.mark.parametrize(
    "usage",
    [None, [], {"cost": None}, {"cost": "0.1"}, {"cost": True}, {"cost": float("nan")}],
    ids=["none", "list", "cost_none", "cost_str", "cost_bool", "cost_nan"],
)
def test_build_step_validates_usage_cost(usage):
    result = JevResult(answers={}, usage=usage, latency_ms=12.4)

    with pytest.raises(ValueError):
        build_step("folder", "none", [], {NONE_OPTION: 1.0}, FOLDER_THRESHOLD, result)


@pytest.mark.parametrize(("usage", "cost"), [({}, 0.0), ({"cost": 0.00001}, 0.00001)])
def test_build_step_reads_cost_and_rounds_latency(usage, cost):
    result = JevResult(answers={}, usage=usage, latency_ms=12.6)

    step = build_step("file", "a", ["a"], {"a": 0.9}, FILE_THRESHOLD, result, labels={"a": "제목"})

    assert step == {
        "kind": "file",
        "verdict": "a",
        "selected": ["a"],
        "labels": {"a": "제목"},
        "probabilities": {"a": 0.9},
        "threshold": FILE_THRESHOLD,
        "latency_ms": 13,
        "cost": cost,
    }


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        (REFUSAL_ANSWER, True),
        (f"  {REFUSAL_ANSWER}\n", True),
        (f'"{REFUSAL_ANSWER}"', True),
        (f"{REFUSAL_ANSWER}.\n", True),
        (f"{REFUSAL_ANSWER}. 다른 문의는 고객센터로 해 주세요.", False),
        (f"죄송합니다. {REFUSAL_ANSWER}", False),
    ],
)
def test_is_refusal_matches_only_whole_answer(answer, expected):
    assert is_refusal(answer) is expected


@pytest.mark.parametrize(
    ("answer", "expected_verdict"),
    [
        (
            {"probabilities": {"supports": 0.4, "contradicts": 0.4, "says_nothing": 0.2}},
            "contradicts",
        ),
        (
            {"probabilities": {"supports": 0.4, "says_nothing": 0.4, "contradicts": 0.2}},
            "says_nothing",
        ),
        ({"choice": "supports"}, "supports"),
    ],
    ids=["supports_vs_contradicts", "supports_vs_says_nothing", "choice_fallback"],
)
def test_read_grounding_uses_argmax_with_conservative_tie_break(answer, expected_verdict):
    verdict, probabilities = read_grounding(answer)

    assert verdict == expected_verdict
    assert verdict in probabilities


def test_format_passages_numbers_and_caps_each_passage():
    long_text = "가" * (MAX_PASSAGE_CHARS + 50)
    passages = [
        {"path": "shipping/a.md", "line": 5, "text": long_text},
        {"path": "returns/b.md", "line": 3, "text": "짧은 본문"},
    ]

    formatted = format_passages(passages)

    first, second = formatted.split("\n\n")
    assert first == f"[1] shipping/a.md:5\n{'가' * MAX_PASSAGE_CHARS}"
    assert second == "[2] returns/b.md:3\n짧은 본문"


# --- graph ------------------------------------------------------------------------
def test_doc_rag_answers_with_supports(corpus_root):
    jev, llm = ScriptedJev(happy_answers()), FakeAnswerLLM()
    graph = build_graph(corpus_root, jev, llm)

    state = run_graph(graph, {"query": "배송비는 얼마인가요?"})

    assert state["error"] is None
    output = state["output"]
    assert output["status"] == "answered"
    assert [step["kind"] for step in output["steps"]] == [
        "folder",
        "file",
        "sufficiency",
        "grounding",
    ]
    assert output["answer"] == ANSWER_TEXT
    assert output["grounding"] == "supports"
    assert len(jev.calls) == 4
    assert len(llm.calls) == 1


def test_doc_rag_two_folders_send_passages_of_both_to_llm(corpus_root):
    answers = happy_answers()
    answers["folder"] = choice_answer(
        {"shipping": FOLDER_THRESHOLD + 0.2, "returns": FOLDER_THRESHOLD + 0.2, NONE_OPTION: 0.0}
    )
    answers["file"] = choice_answer(
        {
            "shipping__delivery_fee": FILE_THRESHOLD + 0.3,
            "returns__refund_policy": FILE_THRESHOLD + 0.2,
            NONE_OPTION: 0.0,
        }
    )
    jev, llm = ScriptedJev(answers), FakeAnswerLLM()
    graph = build_graph(corpus_root, jev, llm)

    output = run_graph(graph, {"query": "배송비 환불"})["output"]

    assert output["folders"] == ["returns", "shipping"]
    file_options = jev.calls[1][1]["file"]["criteria"]
    assert {"shipping__delivery_fee", "returns__refund_policy"} <= set(file_options)
    user_message = llm.calls[0][1][1]
    assert "shipping/delivery_fee.md" in user_message
    assert "returns/refund_policy.md" in user_message


def test_doc_rag_no_folder_stops_before_search_and_llm(corpus_root):
    answers = happy_answers()
    answers["folder"] = choice_answer({NONE_OPTION: 0.6, "shipping": 0.3, "returns": 0.1})
    jev, llm = ScriptedJev(answers), FakeAnswerLLM()
    graph = build_graph(corpus_root, jev, llm)

    state = run_graph(graph, {"query": "배송비는 얼마인가요?"})

    output = state["output"]
    assert output["status"] == "no_folder"
    assert [step["kind"] for step in output["steps"]] == ["folder"]
    assert output["steps"][0]["verdict"] == NONE_OPTION
    assert output["passages"] == []
    assert len(jev.calls) == 1
    assert llm.calls == []


@pytest.mark.parametrize("label", ["contradicts", "says_nothing"])
def test_doc_rag_keeps_answer_when_grounding_is_not_supports(corpus_root, label):
    answers = happy_answers()
    answers["grounding"] = grounding_answer(label)
    graph = build_graph(corpus_root, ScriptedJev(answers), FakeAnswerLLM())

    output = run_graph(graph, {"query": "배송비는 얼마인가요?"})["output"]

    assert output["status"] == "answered"
    assert output["answer"] == ANSWER_TEXT
    assert output["grounding"] == label
    assert output["steps"][-1]["verdict"] == label


def test_generate_answer_sends_fenced_passages_and_system_prompt(corpus_root):
    jev, llm = ScriptedJev(happy_answers()), FakeAnswerLLM()
    graph = build_graph(corpus_root, jev, llm)

    run_graph(graph, {"query": "배송비는 얼마인가요?"})

    system_role, system_text = llm.calls[0][0]
    user_role, user_text = llm.calls[0][1]
    assert (system_role, system_text) == ("system", ANSWER_SYSTEM_PROMPT)
    assert user_role == "user"
    assert "질문: 배송비는 얼마인가요?" in user_text
    fenced = user_text.split("<passages>\n", 1)[1].split("\n</passages>", 1)[0]
    assert "shipping/delivery_fee.md" in fenced
    assert "기본 배송비는 3천 원입니다." in fenced


def test_doc_rag_output_has_exact_contract_keys(corpus_root):
    graph = build_graph(corpus_root, ScriptedJev(happy_answers()), FakeAnswerLLM())

    output = run_graph(graph, {"query": "배송비는 얼마인가요?"})["output"]

    assert set(output) == {
        "status",
        "steps",
        "folders",
        "files",
        "passages",
        "answer",
        "grounding",
    }
    step_keys = {
        "kind",
        "verdict",
        "selected",
        "labels",
        "probabilities",
        "threshold",
        "latency_ms",
        "cost",
    }
    assert all(set(step) == step_keys for step in output["steps"])
    file_step = output["steps"][1]
    assert file_step["labels"] == {
        "shipping__delivery_fee": "배송비 안내",
        "shipping__delivery_time": "배송 기간",
    }
    assert output["files"] == ["shipping/delivery_fee.md"]
    assert set(output["passages"][0]) == {"path", "line", "text"}


def test_langgraph_json_registers_doc_rag():
    config = json.loads((REPO_ROOT / "langgraph.json").read_text(encoding="utf-8"))

    assert config["graphs"]["doc_rag"] == "./jev_agent/rag/graph.py:make_doc_rag"
    assert callable(rag_graph.make_doc_rag)


def test_doc_rag_passes_files_to_retriever_in_probability_order(corpus_root):
    answers = happy_answers()
    answers["file"] = choice_answer(
        {
            "shipping__delivery_time": 0.7,
            "shipping__delivery_fee": FILE_THRESHOLD + 0.05,
            NONE_OPTION: 0.0,
        }
    )
    graph = build_graph(corpus_root, ScriptedJev(answers), FakeAnswerLLM())

    output = run_graph(graph, {"query": "배송"})["output"]

    assert output["files"] == ["shipping/delivery_time.md", "shipping/delivery_fee.md"]
    assert output["passages"][0]["path"] == "shipping/delivery_time.md"


def test_doc_rag_run_after_answered_run_on_same_thread_resets_state(corpus_root):
    jev, llm = ScriptedJev(happy_answers()), FakeAnswerLLM()
    graph = build_graph(corpus_root, jev, llm, checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "thread-1"}}

    first = run_graph(graph, {"query": "배송비는 얼마인가요?"}, config)
    jev.answers["folder"] = choice_answer({NONE_OPTION: 0.8, "shipping": 0.1, "returns": 0.1})
    second = run_graph(graph, {"query": "배송비는 얼마인가요?"}, config)

    assert first["output"]["status"] == "answered"
    output = second["output"]
    assert output["status"] == "no_folder"
    assert len(output["steps"]) == 1
    assert output["answer"] is None
    assert output["grounding"] is None
    assert output["passages"] == []
    assert output["files"] == []


def test_doc_rag_builds_with_real_corpus_when_root_is_omitted():
    graph = build_doc_rag_graph(jev=ScriptedJev(happy_answers()), llm=FakeAnswerLLM())

    assert graph.name == "jev-doc-rag"


# --- stop branches and error paths ----------------------------------------------------
def test_doc_rag_no_file_stops_before_search_and_llm(corpus_root):
    answers = {
        "folder": happy_answers()["folder"],
        "file": choice_answer(
            {NONE_OPTION: 0.6, "shipping__delivery_fee": 0.3, "shipping__delivery_time": 0.1}
        ),
    }
    jev, llm = ScriptedJev(answers), FakeAnswerLLM()
    graph = build_graph(corpus_root, jev, llm)

    output = run_graph(graph, {"query": "배송비는 얼마인가요?"})["output"]

    assert output["status"] == "no_file"
    assert [step["kind"] for step in output["steps"]] == ["folder", "file"]
    assert output["files"] == []
    assert len(jev.calls) == 2
    assert llm.calls == []


@pytest.mark.parametrize("query", ["해외", "?!"], ids=["word_not_in_documents", "no_tokens"])
def test_doc_rag_no_passage_skips_sufficiency_and_llm(corpus_root, query):
    answers = {
        name: answer for name, answer in happy_answers().items() if name in {"folder", "file"}
    }
    jev, llm = ScriptedJev(answers), FakeAnswerLLM()
    graph = build_graph(corpus_root, jev, llm)

    output = run_graph(graph, {"query": query})["output"]

    assert output["status"] == "no_passage"
    assert output["passages"] == []
    assert output["files"] == ["shipping/delivery_fee.md"]
    assert len(jev.calls) == 2
    assert llm.calls == []


@pytest.mark.parametrize(
    "probability",
    [SUFFICIENCY_THRESHOLD - 0.01, SUFFICIENCY_THRESHOLD],
    ids=["below_threshold", "at_threshold"],
)
def test_doc_rag_insufficient_skips_llm(corpus_root, probability):
    answers = happy_answers()
    answers["sufficient"] = noul_answer(probability)
    jev, llm = ScriptedJev(answers), FakeAnswerLLM()
    graph = build_graph(corpus_root, jev, llm)

    output = run_graph(graph, {"query": "배송비는 얼마인가요?"})["output"]

    if probability < SUFFICIENCY_THRESHOLD:
        assert output["status"] == "insufficient"
        assert output["answer"] is None
        assert output["passages"] != []
        assert output["steps"][-1]["kind"] == "sufficiency"
        assert output["steps"][-1]["verdict"] == "insufficient"
        assert llm.calls == []
    else:
        assert output["status"] == "answered"
        assert len(llm.calls) == 1


@pytest.mark.parametrize(
    "content",
    [REFUSAL_ANSWER, f"{REFUSAL_ANSWER}.\n", f'"{REFUSAL_ANSWER}"'],
    ids=["plain", "period_and_newline", "quoted"],
)
def test_doc_rag_llm_refusal_ends_insufficient_without_grounding(corpus_root, content):
    jev, llm = ScriptedJev(happy_answers()), FakeAnswerLLM(content=content)
    graph = build_graph(corpus_root, jev, llm)

    output = run_graph(graph, {"query": "배송비는 얼마인가요?"})["output"]

    assert output["status"] == "insufficient"
    assert output["answer"] is None
    assert output["grounding"] is None
    assert output["passages"] != []
    assert [step["kind"] for step in output["steps"]] == ["folder", "file", "sufficiency"]
    assert output["steps"][-1]["verdict"] == "sufficient"
    assert len(jev.calls) == 3
    assert len(llm.calls) == 1


def test_doc_rag_empty_query_reports_error_without_jev_call(corpus_root):
    jev, llm = ScriptedJev(happy_answers()), FakeAnswerLLM()
    graph = build_graph(corpus_root, jev, llm)

    state = run_graph(graph, {"query": ""})

    assert state["output"] is None
    assert "query" in state["error"]
    assert jev.calls == []


@pytest.mark.parametrize(
    "payload", [None, ["query"], "query", 3], ids=["none", "list", "string", "number"]
)
def test_doc_rag_non_object_payload_reports_error_without_jev_call(corpus_root, payload):
    jev, llm = ScriptedJev(happy_answers()), FakeAnswerLLM()
    graph = build_graph(corpus_root, jev, llm)

    state = run_graph(graph, payload)

    assert state["output"] is None
    assert "payload" in state["error"]
    assert jev.calls == []
    assert llm.calls == []


@pytest.mark.parametrize(("fail_on", "llm_calls"), [(1, 0), (2, 0), (3, 0), (4, 1)])
def test_doc_rag_jev_failure_at_any_call_reports_error(corpus_root, fail_on, llm_calls):
    jev, llm = FailingJev(happy_answers(), fail_on=fail_on), FakeAnswerLLM()
    graph = build_graph(corpus_root, jev, llm)

    state = run_graph(graph, {"query": "배송비는 얼마인가요?"})

    assert state["output"] is None
    assert "402" in state["error"]
    assert len(llm.calls) == llm_calls


def malformed_answers(name: str, answer: Any) -> dict[str, dict[str, Any]]:
    return {**happy_answers(), name: answer}


@pytest.mark.parametrize(
    "make_jev",
    [
        lambda: ScriptedJev(malformed_answers("file", None)),
        lambda: ScriptedJev(malformed_answers("sufficient", {"type": "noul"})),
        lambda: ScriptedJev(
            malformed_answers("folder", {"type": "choice", "probabilities": ["shipping"]})
        ),
        lambda: ScriptedJev(malformed_answers("sufficient", noul_answer(1.5))),
        lambda: ListAnswersJev({}),
    ],
    ids=["file_none", "sufficient_without_noul", "folder_probabilities_list", "noul_1_5", "list"],
)
def test_doc_rag_malformed_jev_answer_reports_error(corpus_root, make_jev):
    graph = build_graph(corpus_root, make_jev(), FakeAnswerLLM())

    state = run_graph(graph, {"query": "배송비는 얼마인가요?"})

    assert state["output"] is None
    assert state["error"]


@pytest.mark.parametrize("usage", [None, [], {"cost": None}], ids=["none", "list", "cost_none"])
def test_doc_rag_malformed_jev_usage_reports_error(corpus_root, usage):
    jev, llm = UsageJev(happy_answers(), usage), FakeAnswerLLM()
    graph = build_graph(corpus_root, jev, llm)

    state = run_graph(graph, {"query": "배송비는 얼마인가요?"})

    assert state["output"] is None
    assert state["error"]
    assert len(jev.calls) == 1
    assert llm.calls == []


def test_doc_rag_llm_failure_reports_error(corpus_root):
    jev, llm = ScriptedJev(happy_answers()), FakeAnswerLLM(fail=True)
    graph = build_graph(corpus_root, jev, llm)

    state = run_graph(graph, {"query": "배송비는 얼마인가요?"})

    assert state["output"] is None
    assert "답변 생성" in state["error"]
    assert "RuntimeError" in state["error"]
    assert "secret detail" not in state["error"]
    assert len(jev.calls) == 3


@pytest.mark.parametrize(
    "content",
    ["", "   \n", [{"type": "text", "text": ANSWER_TEXT}]],
    ids=["empty", "whitespace", "content_blocks"],
)
def test_doc_rag_empty_llm_content_reports_error(corpus_root, content):
    jev, llm = ScriptedJev(happy_answers()), FakeAnswerLLM(content=content)
    graph = build_graph(corpus_root, jev, llm)

    state = run_graph(graph, {"query": "배송비는 얼마인가요?"})

    assert state["output"] is None
    assert "답변 생성" in state["error"]
    assert len(jev.calls) == 3


@pytest.mark.parametrize(
    ("router_name", "next_node"),
    [
        ("route_after_select_folders", "select_files"),
        ("route_after_select_files", "search_passages"),
        ("route_after_search_passages", "judge_sufficiency"),
        ("route_after_judge_sufficiency", "generate_answer"),
        ("route_after_generate_answer", "verify_grounding"),
        ("route_after_verify_grounding", "build_output"),
    ],
)
def test_routers_send_error_to_end_and_status_to_build_output(router_name, next_node):
    router = getattr(rag_graph, router_name)

    assert router({"error": "boom", "status": "answered"}) == "end"
    assert router({"error": "boom"}) == "end"
    assert router({"status": "insufficient"}) == "build_output"
    assert router({"status": None, "error": None}) == next_node


def test_doc_rag_run_after_error_run_on_same_thread_is_clean(corpus_root):
    jev, llm = ScriptedJev(happy_answers()), FakeAnswerLLM()
    graph = build_graph(corpus_root, jev, llm, checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "thread-1"}}

    first = run_graph(graph, {"query": ""}, config)
    second = run_graph(graph, {"query": "배송비는 얼마인가요?"}, config)

    assert first["error"]
    assert second["error"] is None
    assert second["output"]["status"] == "answered"
    assert len(second["output"]["steps"]) == 4
