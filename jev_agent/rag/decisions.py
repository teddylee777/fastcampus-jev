"""문서 RAG 의 Jev 판단 네 가지: 질문을 만들고, 답을 검증해 읽고, 기준값으로 자른다.

Jev 를 직접 부르지 않는 순수 함수만 둔다. 호출은 그래프 노드가 한다.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from jev_agent.jev import JevResult, choice, noul
from jev_agent.rag.corpus import CorpusIndex
from jev_agent.rag.retriever import Passage

NONE_OPTION = "none"  # jev_agent/patterns/actions.py 의 NO_TARGET 과 같은 '해당 없음' 키
NONE_DESCRIPTION = "해당 없음. 위 보기 중 이 질의에 맞는 것이 없다."
# 아래 기준값은 시작값이다. 12번 노트북을 실제로 실행한 뒤에만 조정한다.
FOLDER_THRESHOLD, MAX_FOLDERS = 0.25, 2
FILE_THRESHOLD, MAX_FILES = 0.2, 3
SUFFICIENCY_THRESHOLD = 0.5
MAX_PASSAGE_CHARS = 600
REFUSAL_ANSWER = "문서에서 찾지 못했습니다"  # 답변 프롬프트와 거절 판정이 함께 쓰는 유일한 정의
REFUSAL_TRIM_CHARS = " \t\r\n\"'“”."  # 거절 판정 때 양끝에서 떼는 글자

FOLDER_INSTRUCTIONS = "query 에 답하는 데 필요한 문서가 들어 있을 폴더는 어느 것인가? 맞는 폴더가 없으면 none 을 고른다."
FILE_INSTRUCTIONS = (
    "query 에 답하는 내용이 들어 있을 문서는 어느 것인가? 맞는 문서가 없으면 none 을 고른다."
)
SUFFICIENCY_INSTRUCTIONS = (
    "passages 만 읽고 query 에 답할 수 있는가? 주제만 같고 묻는 내용이 없으면 아니오다."
)
SUFFICIENCY_TRUE = "passages 에 query 의 답이 직접 적혀 있다."
SUFFICIENCY_FALSE = "passages 에 query 의 답이 없거나 일부만 있다."
GROUNDING_INSTRUCTIONS = "answer 의 내용이 passages 에 근거하는가?"
GROUNDING_LABELS = {  # supports 를 맨 뒤에 둔다(첫 옵션 편향이 '근거 있음' 쪽으로 가지 않게)
    "contradicts": "answer 가 passages 의 내용과 어긋난다.",
    "says_nothing": "passages 에 answer 의 내용을 뒷받침하는 문장이 없다.",
    "supports": "answer 의 모든 내용이 passages 에 적혀 있다.",
}
GROUNDING_TIE_ORDER = ("contradicts", "says_nothing", "supports")  # 동점이면 보수적인 쪽

Question = tuple[dict[str, Any], dict[str, dict[str, Any]]]  # (state, questions)


# --- 질문 -------------------------------------------------------------------------
def format_passages(passages: list[Passage]) -> str:
    """충분성·근거 질문과 답변 프롬프트가 함께 쓰는 구절 문자열."""
    return "\n\n".join(
        f"[{number}] {passage['path']}:{passage['line']}\n{passage['text'][:MAX_PASSAGE_CHARS]}"
        for number, passage in enumerate(passages, start=1)
    )


def _with_none_option(options: dict[str, str]) -> dict[str, str]:
    """옵션은 키 이름 순으로 넣고 '해당 없음' 을 마지막에 둔다(첫 옵션 편향 방지)."""
    return {**dict(sorted(options.items())), NONE_OPTION: NONE_DESCRIPTION}


def build_folder_question(index: CorpusIndex, query: str) -> Question:
    options = _with_none_option(
        {folder["name"]: folder["description"] for folder in index["folders"]}
    )
    return {"query": query}, {"folder": choice(FOLDER_INSTRUCTIONS, options)}


def build_file_question(index: CorpusIndex, folders: list[str], query: str) -> Question:
    options = _with_none_option(
        {
            entry["key"]: f"{entry['title']}: {entry['summary']}"
            for entry in index["files"]
            if entry["folder"] in folders
        }
    )
    return {"query": query}, {"file": choice(FILE_INSTRUCTIONS, options)}


def build_sufficiency_question(query: str, passages: list[Passage]) -> Question:
    state = {"query": query, "passages": format_passages(passages)}
    question = noul(SUFFICIENCY_INSTRUCTIONS, SUFFICIENCY_TRUE, SUFFICIENCY_FALSE)
    return state, {"sufficient": question}


def build_grounding_question(answer: str, passages: list[Passage]) -> Question:
    state = {"answer": answer, "passages": format_passages(passages)}
    return state, {"grounding": choice(GROUNDING_INSTRUCTIONS, dict(GROUNDING_LABELS))}


# --- 답 읽기 ----------------------------------------------------------------------
def _is_probability(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and 0 <= value <= 1


def require_mapping(value: Any, message: str) -> Mapping[str, Any]:
    """Jev 가 돌려준 값이 객체가 아니면 호출부가 error 로 바꿀 수 있게 ValueError 를 낸다."""
    if isinstance(value, Mapping):
        return value
    raise ValueError(message)


def read_answer(result: JevResult, name: str) -> Any:
    """질문 이름의 답을 꺼낸다. 이름이 없으면 None 이고 read_* 가 거른다."""
    answers = require_mapping(result.answers, "Jev 응답의 answers 가 객체가 아닙니다.")
    return answers.get(name)


def read_probabilities(answer: Any, offered: list[str]) -> dict[str, float]:
    """choice 답에서 제시한 옵션의 probability 를 읽는다. probabilities 가 없을 때만 choice 를 쓴다."""
    answer = require_mapping(answer, "Jev 의 choice 답이 객체가 아닙니다.")
    if "probabilities" in answer:
        raw = require_mapping(
            answer["probabilities"], "Jev 답의 probabilities 가 객체가 아닙니다."
        )
        kept = {key: raw[key] for key in offered if key in raw}
        if kept:
            if not all(_is_probability(value) for value in kept.values()):
                raise ValueError("Jev 답의 probability 는 0 이상 1 이하의 숫자여야 합니다.")
            return {key: float(value) for key, value in kept.items()}
    picked = answer.get("choice")
    if isinstance(picked, str) and picked in offered:
        return {picked: 1.0}
    raise ValueError("Jev 답에서 제시한 옵션의 probability 를 읽을 수 없습니다.")


def read_noul(answer: Any) -> float:
    value = require_mapping(answer, "Jev 의 noul 답이 객체가 아닙니다.").get("noul")
    if not _is_probability(value):
        raise ValueError("Jev 의 noul 답은 0 이상 1 이하의 숫자여야 합니다.")
    return float(value)


def read_grounding(answer: Any) -> tuple[str, dict[str, float]]:
    """가장 큰 라벨을 고른다. 동점이면 GROUNDING_TIE_ORDER 에서 앞선(보수적인) 라벨이 이긴다."""
    probabilities = read_probabilities(answer, list(GROUNDING_LABELS))
    top = max(probabilities.values())
    verdict = next(label for label in GROUNDING_TIE_ORDER if probabilities.get(label) == top)
    return verdict, probabilities


def is_refusal(answer: str) -> bool:
    """양끝의 공백·따옴표·마침표만 무시하고, 답 전체가 거절 문장일 때만 참이다."""
    return answer.strip(REFUSAL_TRIM_CHARS) == REFUSAL_ANSWER


# --- 선택과 기록 ------------------------------------------------------------------
def select_labels(probabilities: dict[str, float], threshold: float, limit: int) -> list[str]:
    """1등이 '해당 없음'(동점 포함)이면 비운다. 아니면 기준값 이상인 옵션을 limit 개까지 고른다."""
    ranked = sorted(
        probabilities.items(), key=lambda item: (-item[1], item[0] != NONE_OPTION, item[0])
    )
    if not ranked or ranked[0][0] == NONE_OPTION:
        return []
    return [key for key, value in ranked if key != NONE_OPTION and value >= threshold][:limit]


def _finite_float(value: Any) -> float | None:
    """유한한 float 로 바꿀 수 있는 숫자만 돌려준다. bool·비숫자·nan·inf·10**400 같은 큰 정수는 None."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def _read_cost(usage: Any) -> float:
    cost = require_mapping(usage, "Jev 응답의 usage 가 객체가 아닙니다.").get("cost", 0.0)
    number = _finite_float(cost)
    if number is None:
        raise ValueError("Jev 응답의 usage.cost 는 유한한 숫자여야 합니다.")
    return number


def build_step(
    kind: str,
    verdict: str,
    selected: list[str],
    probabilities: dict[str, float],
    threshold: float | None,
    result: JevResult,
    labels: dict[str, str] | None = None,
) -> dict[str, Any]:
    """출력 계약의 step 한 개. cost 는 JevResult.cost 대신 직접 검사해서 만든다."""
    return {
        "kind": kind,
        "verdict": verdict,
        "selected": list(selected),
        "labels": labels or {},
        "probabilities": dict(probabilities),
        "threshold": threshold,
        "latency_ms": round(result.latency_ms),
        "cost": _read_cost(result.usage),
    }
