"""Unit tests for the doc_rag decisions (selection, questions, readers). No network."""

from __future__ import annotations

import pytest

from jev_agent.jev import JevResult
from jev_agent.rag.corpus import CorpusIndex
from jev_agent.rag.decisions import (
    FILE_THRESHOLD,
    FOLDER_THRESHOLD,
    MAX_FILES,
    MAX_FOLDERS,
    MAX_PASSAGE_CHARS,
    NONE_OPTION,
    REFUSAL_ANSWER,
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
    [
        None,
        [],
        {"cost": None},
        {"cost": "0.1"},
        {"cost": True},
        {"cost": float("nan")},
        {"cost": 10**400},
    ],
    ids=["none", "list", "cost_none", "cost_str", "cost_bool", "cost_nan", "cost_unrepresentable"],
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
