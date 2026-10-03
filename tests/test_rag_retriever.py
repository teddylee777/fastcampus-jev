"""Unit tests for the document corpus index and the grep retriever. Temporary documents only; no network."""

from __future__ import annotations

from pathlib import Path

import pytest

from jev_agent.rag.corpus import (
    DOCUMENTS_ROOT,
    INSUFFICIENT_QUERY,
    SAMPLE_QUERIES,
    load_corpus_index,
)
from jev_agent.rag.decisions import MAX_PASSAGE_CHARS
from jev_agent.rag.retriever import read_paragraphs, search_passages, tokenize_query
from tests.fakes import doc


def write_corpus(root: Path, layout: dict[str, dict[str, str]]) -> Path:
    """Write {folder: {file name: content}} under root."""
    for folder, files in layout.items():
        (root / folder).mkdir(parents=True)
        for name, content in files.items():
            (root / folder / name).write_text(content, encoding="utf-8")
    return root


VALID_DOC = doc("제목", "요약입니다.", "본문입니다.")

BROKEN_LAYOUTS = {
    "folder_description_missing": ({"a": {"x.md": VALID_DOC}}, "a/_folder.md"),
    "folder_description_empty": ({"a": {"_folder.md": " \n", "x.md": VALID_DOC}}, "a/_folder.md"),
    "folder_without_documents": ({"a": {"_folder.md": "설명"}}, "a"),
    "title_without_hash_prefix": (
        {"a": {"_folder.md": "설명", "x.md": "제목\n\n요약입니다.\n"}},
        "a/x.md",
    ),
    "summary_paragraph_missing": ({"a": {"_folder.md": "설명", "x.md": "# 제목\n"}}, "a/x.md"),
    "file_name_with_uppercase_and_dash": (
        {"a": {"_folder.md": "설명", "Bad-Name.md": VALID_DOC}},
        "a/Bad-Name.md",
    ),
    "file_name_with_leading_underscore": (
        {"a": {"_folder.md": "설명", "_lead.md": VALID_DOC}},
        "a/_lead.md",
    ),
    "file_name_with_trailing_underscore": (
        {"a": {"_folder.md": "설명", "trail_.md": VALID_DOC}},
        "a/trail_.md",
    ),
    "file_name_with_double_underscore": (
        {"a": {"_folder.md": "설명", "a__b.md": VALID_DOC}},
        "a/a__b.md",
    ),
    "folder_name_with_leading_underscore": (
        {"_lead": {"_folder.md": "설명", "x.md": VALID_DOC}},
        "_lead",
    ),
    "folder_named_none": ({"none": {"_folder.md": "설명", "x.md": VALID_DOC}}, "none"),
}


# --- corpus index ---------------------------------------------------------------
def test_load_corpus_index_real_corpus_has_descriptions_for_every_folder_and_file():
    index = load_corpus_index()

    assert len(index["folders"]) == 5
    assert 10 <= len(index["files"]) <= 12
    assert all(folder["description"].strip() for folder in index["folders"])
    for entry in index["files"]:
        assert entry["title"].strip()
        assert entry["summary"].strip()
        assert not entry["path"].endswith("_folder.md")
    assert {entry["folder"] for entry in index["files"]} == {f["name"] for f in index["folders"]}


@pytest.mark.parametrize(
    ("layout", "path_fragment"),
    BROKEN_LAYOUTS.values(),
    ids=BROKEN_LAYOUTS.keys(),
)
def test_load_corpus_index_rejects_broken_corpus(tmp_path, layout, path_fragment):
    write_corpus(tmp_path, layout)

    with pytest.raises(ValueError) as error:
        load_corpus_index(tmp_path)

    assert str(tmp_path / path_fragment) in str(error.value)


def test_load_corpus_index_reads_utf8_and_excludes_folder_description_file(tmp_path):
    write_corpus(
        tmp_path,
        {
            "shipping": {
                "_folder.md": "배송 안내\n",
                "delivery_fee.md": doc(
                    "배송비 안내", "배송비 기준을 알려 드립니다.", "본문입니다."
                ),
            }
        },
    )

    index = load_corpus_index(tmp_path)

    assert index["folders"] == [{"name": "shipping", "description": "배송 안내"}]
    assert index["files"] == [
        {
            "key": "shipping__delivery_fee",
            "path": "shipping/delivery_fee.md",
            "folder": "shipping",
            "title": "배송비 안내",
            "summary": "배송비 기준을 알려 드립니다.",
        }
    ]
    assert "_folder" not in index["files"][0]["key"]


# --- tokenizer ------------------------------------------------------------------
@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("매장에서는", ["매장"]),
        ("약도", ["약도"]),
        ("배송비는 배송비", ["배송비"]),
        ("Refund 정책이", ["refund", "정책"]),
    ],
)
def test_tokenize_query_strips_one_longest_particle_keeps_short_stems_and_dedupes(query, expected):
    assert tokenize_query(query) == expected


# --- search ---------------------------------------------------------------------
def make_index(tmp_path: Path, files: dict[str, str]):
    """files maps 'folder/stem.md' to content; every folder gets a description."""
    layout: dict[str, dict[str, str]] = {}
    for path, content in files.items():
        folder, name = path.split("/")
        layout.setdefault(folder, {"_folder.md": f"{folder} 설명"})[name] = content
    return load_corpus_index(write_corpus(tmp_path, layout))


def test_search_passages_returns_paragraph_with_path_and_start_line(tmp_path):
    index = make_index(
        tmp_path,
        {"shipping/a.md": doc("제목", "요약입니다.", "첫 본문입니다.", "배송비는 3천 원입니다.")},
    )

    passages = search_passages(index, ["shipping/a.md"], "배송비")

    assert passages == [{"path": "shipping/a.md", "line": 7, "text": "배송비는 3천 원입니다."}]


def test_search_passages_matches_word_with_trailing_particle(tmp_path):
    index = make_index(
        tmp_path,
        {"shipping/a.md": doc("제목", "요약입니다.", "기본 배송비는 3천 원입니다.")},
    )

    passages = search_passages(index, ["shipping/a.md"], "배송비는")

    assert [p["text"] for p in passages] == ["기본 배송비는 3천 원입니다."]


def test_search_passages_orders_by_match_count_then_file_order_then_line_and_caps_at_limit(
    tmp_path,
):
    index = make_index(
        tmp_path,
        {
            "returns/a.md": doc(
                "제목", "요약입니다.", "환불 안내입니다.", "환불 기간 안내입니다."
            ),
            "membership/b.md": doc("제목", "요약입니다.", "환불 적립금 안내입니다."),
        },
    )

    forward = search_passages(index, ["returns/a.md", "membership/b.md"], "환불")
    backward = search_passages(index, ["membership/b.md", "returns/a.md"], "환불")
    capped = search_passages(index, ["returns/a.md", "membership/b.md"], "환불", limit=1)

    assert [p["path"] for p in forward] == ["returns/a.md", "returns/a.md", "membership/b.md"]
    assert [p["line"] for p in forward[:2]] == [5, 7]
    assert [p["path"] for p in backward] == ["membership/b.md", "returns/a.md", "returns/a.md"]
    assert [(p["path"], p["line"]) for p in capped] == [("returns/a.md", 5)]


def test_search_passages_keeps_one_passage_per_matching_file_when_limit_is_tight(tmp_path):
    index = make_index(
        tmp_path,
        {
            "shipping/a.md": doc(
                "제목",
                "요약입니다.",
                "배송비 택배 안내 하나입니다.",
                "배송비 택배 안내 둘입니다.",
                "배송비 택배 안내 셋입니다.",
            ),
            "shipping/b.md": doc("제목", "요약입니다.", "배송비만 적힌 문단입니다."),
        },
    )

    passages = search_passages(index, ["shipping/a.md", "shipping/b.md"], "배송비 택배", limit=3)

    assert "shipping/b.md" in {p["path"] for p in passages}
    assert len(passages) == 3


def test_search_passages_caps_seeds_by_best_match_then_file_order_when_files_exceed_limit(
    tmp_path,
):
    index = make_index(
        tmp_path,
        {
            "shipping/a.md": doc("제목", "요약입니다.", "배송비 안내입니다."),
            "shipping/b.md": doc("제목", "요약입니다.", "배송비 택배 안내입니다."),
            "shipping/c.md": doc("제목", "요약입니다.", "배송비 안내입니다."),
        },
    )

    passages = search_passages(
        index, ["shipping/a.md", "shipping/b.md", "shipping/c.md"], "배송비 택배", limit=2
    )

    assert [p["path"] for p in passages] == ["shipping/b.md", "shipping/a.md"]


def test_search_passages_without_match_returns_empty_list(tmp_path):
    index = make_index(tmp_path, {"shipping/a.md": doc("제목", "요약입니다.", "본문입니다.")})

    assert search_passages(index, ["shipping/a.md"], "존재하지않는낱말") == []


def test_search_passages_query_without_tokens_returns_empty_list(tmp_path):
    index = make_index(tmp_path, {"shipping/a.md": doc("제목", "요약입니다.", "본문입니다.")})

    assert search_passages(index, ["shipping/a.md"], "?!") == []


def test_search_passages_same_input_returns_same_result(tmp_path):
    index = make_index(
        tmp_path,
        {
            "shipping/a.md": doc("제목", "요약입니다.", "배송비 안내입니다."),
            "returns/b.md": doc("제목", "요약입니다.", "배송비 환불 안내입니다."),
        },
    )
    paths = ["shipping/a.md", "returns/b.md"]

    assert search_passages(index, paths, "배송비 환불") == search_passages(
        index, paths, "배송비 환불"
    )


def test_search_passages_unknown_path_raises_value_error(tmp_path):
    index = make_index(tmp_path, {"shipping/a.md": doc("제목", "요약입니다.", "본문입니다.")})

    with pytest.raises(ValueError, match="ghost/none.md"):
        search_passages(index, ["shipping/a.md", "ghost/none.md"], "본문")


def test_read_paragraphs_skips_title_and_rejects_unknown_path(tmp_path):
    index = make_index(tmp_path, {"shipping/a.md": doc("제목", "요약입니다.", "본문입니다.")})

    paragraphs = read_paragraphs(index, "shipping/a.md")

    assert [(p["line"], p["text"]) for p in paragraphs] == [(3, "요약입니다."), (5, "본문입니다.")]
    with pytest.raises(ValueError, match="shipping/zzz.md"):
        read_paragraphs(index, "shipping/zzz.md")


def test_read_paragraphs_file_missing_on_disk_raises_value_error_naming_relative_path(tmp_path):
    index = make_index(tmp_path, {"shipping/a.md": doc("제목", "요약입니다.", "본문입니다.")})
    (tmp_path / "shipping" / "a.md").unlink()

    with pytest.raises(ValueError, match="shipping/a.md") as raised:
        read_paragraphs(index, "shipping/a.md")

    assert str(tmp_path) not in str(raised.value)


# --- real corpus ----------------------------------------------------------------
def test_sample_queries_real_corpus_answerable_have_passages_and_unanswerable_has_none():
    index = load_corpus_index()
    all_paths = [entry["path"] for entry in index["files"]]
    queries = {sample["label"]: sample["query"] for sample in SAMPLE_QUERIES}

    assert search_passages(index, all_paths, queries["정상"])
    both_folders = search_passages(
        index,
        ["returns/refund_timeline.md", "membership/points.md"],
        queries["두 폴더에 걸침"],
    )
    assert {p["path"] for p in both_folders} == {
        "returns/refund_timeline.md",
        "membership/points.md",
    }
    assert search_passages(index, all_paths, queries["문서에 없음"]) == []


def test_insufficient_query_real_corpus_matches_passages_but_no_overseas_text():
    index = load_corpus_index()
    all_paths = [entry["path"] for entry in index["files"]]

    assert search_passages(index, all_paths, INSUFFICIENT_QUERY)
    assert search_passages(index, all_paths, "해외") == []


def test_real_documents_every_paragraph_fits_max_passage_chars():
    index = load_corpus_index()

    for entry in index["files"]:
        for paragraph in read_paragraphs(index, entry["path"]):
            assert len(paragraph["text"]) <= MAX_PASSAGE_CHARS, entry["path"]


def test_documents_root_points_inside_the_package():
    assert DOCUMENTS_ROOT.is_dir()
    assert DOCUMENTS_ROOT.name == "documents"
