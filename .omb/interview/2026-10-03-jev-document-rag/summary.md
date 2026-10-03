---
title: "문서 기반 RAG 에 Jev 적용"
date: 2026-10-03
language: ko
status: accepted
revision: 2
accepted_revision: 2
accepted_at: 2026-10-04
acceptance_quote: "A 로 하겠습니다."
max_questions: 40
questions_asked: 10
baseline:
  - repo: "teddylee777/fastcampus-jev"
    ref: "main"
    sha: "e36edabb4f8b71c845c6ee67eb0ed47f9a313c3a"
    worktree_dirty: true
---

# 문서 기반 RAG 에 Jev 적용 — 인터뷰 요약

## Brief

사용자는 문서 기반 검색(RAG)에서도 Jev 를 쓰고 싶어 했고, 웹 리서치로 적용 방법을 조사한 뒤
앱에 반영해 달라고 요청했다. 조사 결과 공식 cookbook 과 커뮤니티 프로젝트가 Jev 를 소스 라우팅,
chunk 판정, rerank, 충분성 판단, 근거 검증에 쓰고 있었다. 회의에서는 폴더로 나눈 `.md` 문서를
파일 기반 grep 으로 검색하고, Jev 가 폴더 선택, 파일 선택, 충분성, 근거 검증을 맡는 새 LangGraph
그래프를 만들기로 했다. 전용 탭, 12번 노트북, 최소 CI 를 함께 넣고 PR 하나로 한 번에 구현한다.

## Scope and non-goals

범위에 드는 것:

- 폴더로 구조를 잡은 임의의 `.md` 문서 묶음과 폴더·파일 설명
- 파일 기반 grep 검색기
- Jev 판단 4종(폴더 선택, 파일 선택, 충분성, 근거 검증)과 LLM 답변 생성으로 이어지는 RAG 그래프
- 프론트엔드 "문서 RAG" 탭
- 12번 노트북(실제 API 실행 출력 포함)과 README 갱신
- 최소 CI 워크플로(ruff, 오프라인 pytest, vitest)

범위에서 뺀 것:

- chunk 별 관련도 판정과 문서 안 인젝션 판정 (기존 라우팅 탭, 가드레일과 겹침)
- 임베딩이나 벡터 저장소, BM25
- 고객지원 에이전트(`jev_agent/agent.py`)와 `search_faq` 변경
- Jev 확신도가 낮을 때 LLM 으로 넘기는 캐스케이드
- 질의 재작성과 재검색 루프

## Decision ledger index

| Decision | Issue | Adopted direction | Related P-IDs / T-IDs |
|---|---|---|---|
| D-001 | 기준 브랜치 부재 | `origin/main` 에 첫 커밋 `e36edabb` 가 올라가 해결됨 | P-013 |
| D-002 | CI 체크가 없어 자동 병합 불가 | 최소 CI 를 추가 | P-011, T-001 |
| D-003 | `--codex` 의 의미 | Codex 는 리뷰어로만 사용 | P-013 |
| D-004 | RAG 를 앱 어디에 넣을지 | 새 RAG 그래프와 전용 탭, 노트북. 고객지원 에이전트는 유지 | P-008, P-009, P-010, T-003, T-004, T-005 |
| D-005 | 1차 검색기 | 파일 기반 grep. 폴더 구조를 잘 잡고 폴더·파일 선택에 Jev 사용 | P-002, P-003, P-004, T-002, T-003 |
| D-006 | 대상 문서 | 간단한 `.md` 파일을 임의로 생성 | P-001, T-002 |
| D-007 | 검색 이후 Jev 의 역할 | 답변 앞에 충분성, 답변 뒤에 근거 검증 | P-005, P-006, P-007, T-003 |
| D-008 | 폴더·파일 선택 폭 | 확률 기준으로 폴더 최대 2개, 파일 최대 3개. "해당 없음"이면 검색 없이 종료 | P-003, P-004, T-003 |
| D-009 | 노트북 완료 기준 | 실제 API 로 실행해 출력 저장, 자동 병합 | P-010, T-005 |
| D-010 | PR 분할 | 한 번에 전부 구현. 단위 하나, PR 하나 | P-013, T-001~T-005 |
| D-011 | 파일 선택 질문 구성 (2026-10-04, 검증 중 수정) | 선택된 폴더마다 `choice` 질문을 하나씩 만들어 한 번의 호출로 보낸다. 질문 하나로 묻던 방식은 실제 호출에서 한 파일에 확률이 몰려 S-002 를 충족하지 못했다 | P-004, S-002 |

Alternatives and reasons are recorded only in the "Decisions and rationale" section of
`policy.md`.

## Unresolved items

정책 결정으로 남은 것은 없다. 구현 중 확인할 근거가 세 가지 있고, 모두 구현을 막지 않는다.

- 한국어 질의에서 Jev 확률 분포가 어떻게 나오는지 다룬 자료가 없다. 폴더·파일 선택 기준값과
  충분성 기준값은 시작값으로 두고, 12번 노트북을 실제 실행할 때 조정한다 (T-005).
- 저장소에 Codex GitHub 앱이 설치되어 있는지 확인하지 못했다. 설치되어 있지 않으면 PR 감시의
  Codex 리뷰 대기가 시간 초과로 끝난다.
- 웹 리서치의 수치(가격, 지연 시간, 벤치마크 점수)는 요약 도구로 읽은 값이라 원문과 다를 수
  있다. 노트북이나 README 에 넣을 때는 원문을 다시 확인한다.

## knowledge_context

- Adopted evidence:
  - 저장소 코드 `teddylee777/fastcampus-jev@e36edabb` (`jev_agent/jev.py`, `jev_agent/patterns/routing.py`,
    `jev_agent/patterns/__init__.py`, `jev_agent/pattern_graphs.py`, `langgraph.json`,
    `frontend/src/App.tsx`, `frontend/src/lib/langgraph.ts`, `pyproject.toml`, `README.md`)
  - TypeSafe cookbook: `classifying_rag_passages`, `rerank_typesafe`, `semantic_find`,
    `citation_check`, `parallel_questions` (https://docs.typesafe.ai/cookbooks/)
  - TypeSafe 모델 한계 문서 https://docs.typesafe.ai/model-jaggedness/jev-1.13.md
  - OpenRouter Jev 문서 https://openrouter.ai/docs/guides/community/jev
  - 커뮤니티 저장소 jev-search, jev-demo-rag, jev-rag-benchmark, jev-search-rerank-eval
- Rejected evidence:
  - OMB 지식 번들(`omb context build`): wiki 와 운영 메모리가 없어 `unavailable` 로 반환됨
  - LangGraph Adaptive RAG 페이지: 리다이렉트만 반환되어 읽지 못함
- Unresolved: 위 "Unresolved items" 의 세 항목

## Documents

- Summary: .omb/interview/2026-10-03-jev-document-rag/summary.md
- Policy: .omb/interview/2026-10-03-jev-document-rag/policy.md
- Development guide: .omb/interview/2026-10-03-jev-document-rag/development-guide.md

## Acceptance record

Revision 1 을 2026-10-03 에 사용자가 승인했다. 사용자의 답: "승인합니다!"

## Next step

이 기록은 ultra-goal 로드맵의 입력이다. 로드맵은 단위 하나(전체 구현)로 작성하고, 사용자 승인 뒤
예약된 틱이 `omb-goal --unattended` 로 실행한다. 기록은 기본 체크아웃의 `main` 에 커밋되지 않은
상태로 있으며, 기본 체크아웃에서는 `omb-pr` 이 이 기록을 제외하므로 PR 에 실리지 않는다.
