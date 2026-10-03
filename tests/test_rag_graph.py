"""Unit tests for the doc_rag graph. A scripted Jev and a fake LLM are used; no network."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

import jev_agent.rag.graph as rag_graph
from jev_agent.jev import JevClient, JevError, JevResult
from jev_agent.rag.decisions import (
    FILE_THRESHOLD,
    FOLDER_THRESHOLD,
    MAX_FILES,
    NONE_OPTION,
    REFUSAL_ANSWER,
    SUFFICIENCY_THRESHOLD,
)
from jev_agent.rag.graph import ANSWER_SYSTEM_PROMPT, build_doc_rag_graph
from tests.fakes import ScriptedJev, doc

REPO_ROOT = Path(__file__).resolve().parent.parent
ANSWER_TEXT = "배송비는 3천 원입니다."


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
        "files__shipping": choice_answer(
            {"shipping__delivery_fee": 0.8, "shipping__delivery_time": 0.1, NONE_OPTION: 0.1}
        ),
        "sufficient": noul_answer(0.9),
        "grounding": grounding_answer(),
    }


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
    answers["files__shipping"] = choice_answer(
        {
            "shipping__delivery_fee": FILE_THRESHOLD + 0.3,
            "shipping__delivery_time": 0.0,
            NONE_OPTION: 0.0,
        }
    )
    answers["files__returns"] = choice_answer(
        {"returns__refund_policy": FILE_THRESHOLD + 0.2, NONE_OPTION: 0.0}
    )
    jev, llm = ScriptedJev(answers), FakeAnswerLLM()
    graph = build_graph(corpus_root, jev, llm)

    output = run_graph(graph, {"query": "배송비 환불"})["output"]

    assert output["folders"] == ["returns", "shipping"]
    assert len(jev.calls) == 4
    file_questions = jev.calls[1][1]
    assert set(file_questions) == {"files__returns", "files__shipping"}
    assert set(file_questions["files__returns"]["criteria"]) == {
        "returns__refund_policy",
        NONE_OPTION,
    }
    assert set(file_questions["files__shipping"]["criteria"]) == {
        "shipping__delivery_fee",
        "shipping__delivery_time",
        NONE_OPTION,
    }
    assert output["files"] == ["shipping/delivery_fee.md", "returns/refund_policy.md"]
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
        "none__shipping": "해당 없음 (shipping)",
    }
    assert NONE_OPTION not in file_step["probabilities"]
    assert "none__shipping" in file_step["probabilities"]
    assert output["files"] == ["shipping/delivery_fee.md"]
    assert set(output["passages"][0]) == {"path", "line", "text"}


def test_langgraph_json_registers_doc_rag():
    config = json.loads((REPO_ROOT / "langgraph.json").read_text(encoding="utf-8"))

    assert config["graphs"]["doc_rag"] == "./jev_agent/rag/graph.py:make_doc_rag"
    assert callable(rag_graph.make_doc_rag)


def test_doc_rag_passes_files_to_retriever_in_probability_order(corpus_root):
    answers = happy_answers()
    answers["files__shipping"] = choice_answer(
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
def two_folder_answers() -> dict[str, dict[str, Any]]:
    """Folder answer that selects both folders; per-folder file answers are the happy ones."""
    return {
        **happy_answers(),
        "folder": choice_answer(
            {
                "shipping": FOLDER_THRESHOLD + 0.2,
                "returns": FOLDER_THRESHOLD + 0.2,
                NONE_OPTION: 0.0,
            }
        ),
        "files__returns": choice_answer({"returns__refund_policy": 0.8, NONE_OPTION: 0.2}),
    }


def shipping_none_on_top() -> dict[str, Any]:
    return choice_answer(
        {NONE_OPTION: 0.6, "shipping__delivery_fee": 0.3, "shipping__delivery_time": 0.1}
    )


def returns_none_on_top() -> dict[str, Any]:
    return choice_answer({NONE_OPTION: 0.9, "returns__refund_policy": 0.1})


@pytest.mark.parametrize(
    "answers",
    [
        {
            "folder": happy_answers()["folder"],
            "files__shipping": shipping_none_on_top(),
        },
        {
            **two_folder_answers(),
            "files__shipping": shipping_none_on_top(),
            "files__returns": returns_none_on_top(),
        },
    ],
    ids=["one_folder_none", "both_folders_none"],
)
def test_doc_rag_no_file_stops_before_search_and_llm(corpus_root, answers):
    jev, llm = ScriptedJev(answers), FakeAnswerLLM()
    graph = build_graph(corpus_root, jev, llm)

    output = run_graph(graph, {"query": "배송비는 얼마인가요?"})["output"]

    assert output["status"] == "no_file"
    assert [step["kind"] for step in output["steps"]] == ["folder", "file"]
    assert output["steps"][1]["selected"] == []
    assert output["files"] == []
    assert len(jev.calls) == 2
    assert llm.calls == []


def test_doc_rag_file_step_flattens_folder_questions_into_one_step(corpus_root):
    answers = {
        **two_folder_answers(),
        "files__returns": choice_answer({"returns__refund_policy": 0.7, NONE_OPTION: 0.3}),
    }
    graph = build_graph(corpus_root, ScriptedJev(answers), FakeAnswerLLM())

    output = run_graph(graph, {"query": "배송비 환불"})["output"]

    file_steps = [step for step in output["steps"] if step["kind"] == "file"]
    assert len(file_steps) == 1
    file_step = file_steps[0]
    assert list(file_step["probabilities"]) == [
        "returns__refund_policy",
        "none__returns",
        "shipping__delivery_fee",
        "shipping__delivery_time",
        "none__shipping",
    ]
    assert set(file_step["labels"]) == set(file_step["probabilities"])
    assert file_step["labels"]["none__returns"] == "해당 없음 (returns)"
    assert file_step["selected"] == ["shipping__delivery_fee", "returns__refund_policy"]
    assert file_step["verdict"] == "shipping__delivery_fee, returns__refund_policy"


def test_doc_rag_one_folder_none_other_folder_selects_continues(corpus_root):
    answers = {**two_folder_answers(), "files__returns": returns_none_on_top()}
    graph = build_graph(corpus_root, ScriptedJev(answers), FakeAnswerLLM())

    output = run_graph(graph, {"query": "배송비 환불"})["output"]

    assert output["status"] == "answered"
    assert output["files"] == ["shipping/delivery_fee.md"]


def test_doc_rag_merges_files_across_folders_by_probability_and_caps_at_max_files(corpus_root):
    (corpus_root / "returns" / "exchange.md").write_text(
        doc("교환 안내", "교환 안내입니다.", "교환은 배송 후 7일 안에 신청합니다."),
        encoding="utf-8",
    )
    answers = {
        **two_folder_answers(),
        "files__shipping": choice_answer(
            {
                "shipping__delivery_fee": 0.6,
                "shipping__delivery_time": FILE_THRESHOLD + 0.05,
                NONE_OPTION: 0.0,
            }
        ),
        "files__returns": choice_answer(
            {"returns__refund_policy": 0.7, "returns__exchange": 0.4, NONE_OPTION: 0.0}
        ),
    }
    graph = build_graph(corpus_root, ScriptedJev(answers), FakeAnswerLLM())

    output = run_graph(graph, {"query": "배송 환불 교환"})["output"]

    assert len(output["files"]) == MAX_FILES
    assert output["files"] == [
        "returns/refund_policy.md",
        "shipping/delivery_fee.md",
        "returns/exchange.md",
    ]
    assert "shipping/delivery_time.md" not in output["files"]


@pytest.mark.parametrize(
    "broken",
    [None, {"type": "choice", "probabilities": ["returns__refund_policy"]}],
    ids=["missing_answer", "probabilities_list"],
)
def test_doc_rag_missing_answer_for_one_folder_question_reports_error(corpus_root, broken):
    answers = {**two_folder_answers(), "files__returns": broken}
    jev, llm = ScriptedJev(answers), FakeAnswerLLM()
    graph = build_graph(corpus_root, jev, llm)

    state = run_graph(graph, {"query": "배송비 환불"})

    assert set(jev.calls[1][1]) == {"files__returns", "files__shipping"}
    assert state["output"] is None
    assert state["error"]
    assert len(jev.calls) == 2
    assert llm.calls == []


@pytest.mark.parametrize("query", ["해외", "?!"], ids=["word_not_in_documents", "no_tokens"])
def test_doc_rag_no_passage_skips_sufficiency_and_llm(corpus_root, query):
    answers = {
        name: answer
        for name, answer in happy_answers().items()
        if name in {"folder", "files__shipping"}
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
        lambda: ScriptedJev(malformed_answers("files__shipping", None)),
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


def real_jev_client(body: Any) -> JevClient:
    """A real JevClient whose HTTP layer returns `body` as JSON with status 200; no network."""
    payload = json.dumps(body).encode()
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=payload))
    return JevClient(api_key="test-key", async_transport=transport)


@pytest.mark.parametrize(
    "body",
    [["answers"], "answers", None, 3],
    ids=["list_with_answers_word", "string_with_answers_word", "null", "number"],
)
def test_doc_rag_non_object_jev_body_reports_error(corpus_root, body):
    graph = build_doc_rag_graph(jev=real_jev_client(body), llm=FakeAnswerLLM(), root=corpus_root)

    state = run_graph(graph, {"query": "배송비는 얼마인가요?"})

    assert state["output"] is None
    assert state["error"]


def test_doc_rag_unrepresentable_usage_cost_in_real_response_reports_error(corpus_root):
    body = {"answers": {"folder": happy_answers()["folder"]}, "usage": {"cost": 10**400}}
    llm = FakeAnswerLLM()
    graph = build_doc_rag_graph(jev=real_jev_client(body), llm=llm, root=corpus_root)

    state = run_graph(graph, {"query": "배송비는 얼마인가요?"})

    assert state["output"] is None
    assert "usage.cost" in state["error"]
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


# --- unreadable corpus file and malformed LLM response ---------------------------------
def test_doc_rag_corpus_file_removed_after_indexing_reports_error(corpus_root):
    jev, llm = ScriptedJev(happy_answers()), FakeAnswerLLM()
    graph = build_graph(corpus_root, jev, llm)
    (corpus_root / "shipping" / "delivery_fee.md").unlink()

    state = run_graph(graph, {"query": "배송비는 얼마인가요?"})

    assert state["output"] is None
    assert "shipping/delivery_fee.md" in state["error"]
    assert str(corpus_root) not in state["error"]
    assert len(jev.calls) == 2
    assert llm.calls == []


def test_doc_rag_llm_response_without_content_reports_error(corpus_root):
    class ContentlessLLM(FakeAnswerLLM):
        async def ainvoke(self, messages):
            self.calls.append(messages)
            return "plain string, not a message"

    jev, llm = ScriptedJev(happy_answers()), ContentlessLLM()
    graph = build_graph(corpus_root, jev, llm)

    state = run_graph(graph, {"query": "배송비는 얼마인가요?"})

    assert state["output"] is None
    assert "답변 생성" in state["error"]
    assert "AttributeError" in state["error"]
    assert len(jev.calls) == 3


# --- server loading --------------------------------------------------------------------
@pytest.fixture
def server_blockbuster():
    """The blockbuster configuration `langgraph dev` turns on, switched off again afterwards."""
    from langgraph_runtime_inmem.queue import _enable_blockbuster

    blockbuster = _enable_blockbuster()
    yield blockbuster
    blockbuster.deactivate()


def test_registered_doc_rag_factory_does_not_block_the_event_loop(
    server_blockbuster, monkeypatch
):
    from langgraph_api.asyncio import as_asynccontextmanager

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    registered = json.loads((REPO_ROOT / "langgraph.json").read_text(encoding="utf-8"))["graphs"][
        "doc_rag"
    ]
    factory = getattr(rag_graph, registered.rsplit(":", 1)[1])

    async def load_like_the_server():
        value = factory()  # the server calls the factory on its event loop, then awaits the result
        async with as_asynccontextmanager(value) as graph:
            return graph

    graph = asyncio.run(load_like_the_server())

    assert graph.name == "jev-doc-rag"
