"""검색 대상 문서 묶음의 색인. 폴더·파일 설명만 읽고, 본문은 검색 때 읽는다."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TypedDict

DOCUMENTS_ROOT = Path(__file__).resolve().parent / "documents"
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
FOLDER_DESCRIPTION_FILE = "_folder.md"
RESERVED_FOLDER_NAME = "none"  # Jev 선택지의 '해당 없음' 키와 겹치면 안 된다.


class CorpusFolder(TypedDict):
    name: str
    description: str


class CorpusFile(TypedDict):
    key: str  # f"{folder}__{stem}", Jev choice 옵션 키
    path: str  # DOCUMENTS_ROOT 기준 상대 경로 "folder/stem.md"
    folder: str
    title: str
    summary: str


class CorpusIndex(TypedDict):
    root: str
    folders: list[CorpusFolder]  # 이름 순
    files: list[CorpusFile]  # path 순


# 골든 셋. 노트북은 이 목록을 import 하고 탭 예시 칩은 같은 문장을 베껴 쓴다(이 목록이 기준).
# expected 는 "answered" 또는 "stopped". stopped 는 종료 사유 네 가지 중 어느 것이든 되고 답이 없다는 뜻이다.
SAMPLE_QUERIES: list[dict[str, str]] = [
    {"label": "정상", "query": "배송비는 얼마인가요?", "expected": "answered"},
    {
        "label": "두 폴더에 걸침",
        "query": "환불하면 사용한 적립금은 어떻게 되나요?",
        "expected": "answered",
    },
    {"label": "문서에 없음", "query": "주차장 약도를 팩스로 보내주세요", "expected": "stopped"},
]
# 구절은 잡히지만 답은 없는 질의. 노트북의 충분성 절만 쓴다(탭 예시는 위 세 개).
INSUFFICIENT_QUERY = "해외 배송비는 얼마인가요?"


def split_paragraphs(text: str) -> list[tuple[int, str]]:
    """빈 줄 기준 문단을 (시작 줄 번호, 본문) 으로 나눈다. '#' 로 시작하는 제목 줄은 뺀다."""
    paragraphs: list[tuple[int, str]] = []
    start = 0
    block: list[str] = []
    for number, line in enumerate([*text.splitlines(), ""], start=1):
        if line.startswith("#"):
            continue
        if line.strip():
            if not block:
                start = number
            block.append(line.strip())
        elif block:
            paragraphs.append((start, "\n".join(block)))
            block = []
    return paragraphs


def _check_name(name: str, path: Path) -> None:
    if not NAME_PATTERN.fullmatch(name):
        raise ValueError(
            f"이름 '{name}' 은 소문자·숫자·밑줄(앞뒤와 연속 밑줄 제외)만 쓸 수 있습니다: {path}"
        )


def _read_folder_description(folder_dir: Path) -> str:
    description_path = folder_dir / FOLDER_DESCRIPTION_FILE
    if not description_path.is_file():
        raise ValueError(f"폴더 설명 파일이 없습니다: {description_path}")
    description = description_path.read_text(encoding="utf-8").strip()
    if not description:
        raise ValueError(f"폴더 설명 파일이 비어 있습니다: {description_path}")
    return description


def _read_file_entry(root: Path, folder: str, file_path: Path) -> CorpusFile:
    _check_name(file_path.stem, file_path)
    text = file_path.read_text(encoding="utf-8")
    first_line = text.splitlines()[0] if text.strip() else ""
    title = first_line[2:].strip() if first_line.startswith("# ") else ""
    if not title:
        raise ValueError(f"문서 1행은 '# 제목' 이어야 합니다: {file_path}")
    paragraphs = split_paragraphs(text)
    if not paragraphs:
        raise ValueError(f"제목 다음에 요약 문단이 있어야 합니다: {file_path}")
    return {
        "key": f"{folder}__{file_path.stem}",
        "path": file_path.relative_to(root).as_posix(),
        "folder": folder,
        "title": title,
        "summary": paragraphs[0][1],
    }


def load_corpus_index(root: Path = DOCUMENTS_ROOT) -> CorpusIndex:
    """root 아래 폴더와 문서를 읽어 색인을 만든다. 깨진 묶음은 조용히 건너뛰지 않고 ValueError 를 낸다."""
    folders: list[CorpusFolder] = []
    files: list[CorpusFile] = []
    for folder_dir in sorted(entry for entry in root.iterdir() if entry.is_dir()):
        name = folder_dir.name
        _check_name(name, folder_dir)
        if name == RESERVED_FOLDER_NAME:
            raise ValueError(
                f"폴더 이름 '{name}' 은 '해당 없음' 선택지와 겹쳐 쓸 수 없습니다: {folder_dir}"
            )
        description = _read_folder_description(folder_dir)
        document_paths = sorted(
            path for path in folder_dir.glob("*.md") if path.name != FOLDER_DESCRIPTION_FILE
        )
        if not document_paths:
            raise ValueError(f"폴더에 문서 파일이 하나도 없습니다: {folder_dir}")
        folders.append({"name": name, "description": description})
        files.extend(_read_file_entry(root, name, path) for path in document_paths)
    files.sort(key=lambda entry: entry["path"])
    return {"root": str(root), "folders": folders, "files": files}
