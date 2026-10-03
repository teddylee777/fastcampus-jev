"""선택된 파일에서 질의 낱말이 든 문단을 찾는 grep 검색기. 임베딩이나 색인 없이 부분 문자열로만 맞춘다."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TypedDict

from jev_agent.rag.corpus import CorpusIndex, split_paragraphs


class Passage(TypedDict):
    path: str  # DOCUMENTS_ROOT 기준 상대 경로
    line: int  # 문단 시작 줄 (1부터)
    text: str


# 긴 것을 먼저 둔다. 낱말 끝의 조사를 하나만 떼는 데 쓴다.
PARTICLES = (
    "으로는",
    "에서는",
    "으로",
    "에서",
    "에게",
    "까지",
    "부터",
    "이나",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "에",
    "의",
    "도",
    "로",
    "와",
    "과",
    "만",
)
MIN_TOKEN_CHARS = 2


def _strip_particle(word: str) -> str:
    for particle in PARTICLES:
        if word.endswith(particle) and len(word) - len(particle) >= MIN_TOKEN_CHARS:
            return word[: -len(particle)]
    return word


def tokenize_query(query: str) -> list[str]:
    """질의를 검색 낱말로 쪼갠다. 조사를 하나 떼고, 너무 짧은 낱말과 중복은 버린다."""
    words = re.findall(r"[0-9a-z가-힣]+", query.lower())
    stems = (_strip_particle(word) for word in words)
    return list(dict.fromkeys(stem for stem in stems if len(stem) >= MIN_TOKEN_CHARS))


def _require_known_path(index: CorpusIndex, path: str) -> None:
    if path not in {entry["path"] for entry in index["files"]}:
        raise ValueError(f"색인에 없는 문서 경로입니다: {path}")


def read_paragraphs(index: CorpusIndex, path: str) -> list[Passage]:
    """색인에 있는 문서 하나를 문단 단위 구절로 돌려준다."""
    _require_known_path(index, path)
    try:
        text = (Path(index["root"]) / path).read_text(encoding="utf-8")
    except OSError as exc:  # 색인을 만든 뒤 파일이 지워지거나 권한이 바뀐 경우
        raise ValueError(f"문서를 읽지 못했습니다: {path}") from exc
    return [{"path": path, "line": line, "text": body} for line, body in split_paragraphs(text)]


def search_passages(
    index: CorpusIndex, file_paths: list[str], query: str, limit: int = 6
) -> list[Passage]:
    """file_paths(Jev probability 순) 안에서 질의 낱말이 든 문단을 찾는다.

    정렬 키는 (-일치 낱말 수, file_paths 안의 위치, 줄 번호). 일치가 있는 파일마다 가장 앞선
    문단 하나를 먼저 limit 까지 담고, 남는 자리를 나머지 문단으로 채운다.
    """
    for path in file_paths:
        _require_known_path(index, path)
    tokens = tokenize_query(query)
    if not tokens:
        return []

    scored: list[tuple[tuple[int, int, int], Passage]] = []
    for position, path in enumerate(dict.fromkeys(file_paths)):
        for passage in read_paragraphs(index, path):
            lowered = passage["text"].lower()
            matches = sum(1 for token in tokens if token in lowered)
            if matches:
                scored.append(((-matches, position, passage["line"]), passage))
    scored.sort(key=lambda item: item[0])

    best_per_file: dict[str, int] = {}
    for rank, (_, passage) in enumerate(scored):
        best_per_file.setdefault(passage["path"], rank)
    seeds = sorted(best_per_file.values(), key=lambda rank: scored[rank][0][:2])[:limit]
    chosen = set(seeds)
    for rank in range(len(scored)):
        if len(chosen) >= limit:
            break
        chosen.add(rank)
    return [scored[rank][1] for rank in sorted(chosen)]
