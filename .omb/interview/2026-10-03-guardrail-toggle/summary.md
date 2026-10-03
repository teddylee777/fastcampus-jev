---
title: "가드레일 켜기/끄기 스위치 결함 수정"
date: 2026-10-03
language: ko
status: accepted
revision: 1
accepted_revision: 1
accepted_at: 2026-10-03
acceptance_quote: "A 수락합니다."
max_questions: null
questions_asked: 2
baseline:
  - repo: "fastcampus-jev (primary checkout)"
    ref: "main"
    sha: "bb1bccd4163738353de70f3b5510146fce3f0052"
    worktree_dirty: true
---

# 가드레일 켜기/끄기 스위치 결함 수정 — 인터뷰 요약

## Brief

사용자는 고객지원 에이전트 화면의 가드레일 스위치가 "잘 동작하지 않는다"고 보고했고, 직접 검증하면서
고치라고 요청했다. 실행 중인 서버와 화면을 직접 조작해 본 결과 스위치 값의 전달과 서버 반영은
정상이었다. 대신 스위치 상태와 화면 표시 또는 검사 결과가 어긋나는 결함 세 가지를 확인했고,
이 세 가지를 고치기로 합의했다.

1. 스위치가 꺼져 있어도 진행 문구가 "입력을 검사하는 중", "입력 검사 통과"로 나온다.
2. 위험 도구(`cancel_order`, `request_refund`)의 결과는 스위치와 무관하게 가드레일 검사를 받지 않고
   판단 패널에 기록도 남지 않는다.
3. 스위치가 꺼져 있어도 예시 카드의 힌트가 "가드레일: 차단"처럼 켜진 상태의 결과를 약속한다.

## Scope and non-goals

범위는 고객지원 에이전트(`support` 그래프)의 가드레일 스위치와 그 표시다.

- 포함: `jev_agent/guardrails.py` 의 도구 결과 검사, `frontend/src/chat/` 의 진행 문구와 예시 힌트,
  이를 설명하는 `README.md` 샘플 앱 절.
- 제외: 스위치 값을 새 대화나 새로고침 뒤에도 유지하는 일. 지금처럼 "켜짐"으로 돌아간다 (P-007).
- 제외: 시스템 프롬프트와 LLM 자체의 거절 동작. 스위치를 꺼도 LLM 이 인젝션 문장을 스스로 거절할 수
  있고, 이는 가드레일이 아니라 모델의 동작이다.
- 제외: 가드레일 비교 탭(`guardrail_lab` 그래프), 범주별 기준값과 조치, 노트북.
- 열린 PR 은 없다.

## Decision ledger index

| Decision | Issue | Adopted direction | Related P-IDs / T-IDs |
|---|---|---|---|
| D-001 | 수정 범위 | 확인된 결함 1, 2, 3번을 고치고 스위치 값 보존(4번)은 현재 동작을 유지한다 | P-003, P-005, P-006, P-007 / T-001, T-002, T-003 |
| D-002 | 이미 실행된 위험 도구의 결과가 검사에 걸리거나 검사가 실패했을 때 LLM 에 넘길 내용 | 원문을 지우고 "작업은 이미 실행되었다"는 사실을 담은 위험 도구 전용 문구로 바꾼다 | P-004 / T-001 |

대안과 사유는 `policy.md` 의 "결정과 근거" 절에만 적는다.

## Unresolved items

없음. 두 결정이 모두 확정됐고, 판단에 필요한 근거는 모두 확인했다.

## knowledge_context

- Bundle: `3ee4fda708cbe0ecee7c57744b861266c04cb99d0c1bccc842abb8caf862cd00` (workflow interview).
  wiki 와 운영 메모리는 이 저장소에 없어 `unavailable` 로 돌아왔다 (`missing_wiki`, `missing_memory`).
- Adopted evidence
  - E-01 `jev_agent/guardrails.py:88-99, 236-260, 262-312` 스위치 판정과 입력/도구 결과 검사
  - E-02 `jev_agent/middleware.py:281-324` 위험 게이트가 결과를 `Command` 로 감싸 돌려주는 경로
  - E-03 `jev_agent/agent.py:56-60` 미들웨어 순서 (가드레일이 가장 바깥)
  - E-04 `frontend/src/chat/ChatTab.tsx:20-44, 68, 81-107, 118-126, 187` 스위치, 실행 설정, 예시 카드
  - E-05 `frontend/src/chat/timeline.ts:101-115` 진행 문구
  - E-06 `frontend/src/App.tsx:27-30, 85` 새 대화가 채팅 컴포넌트를 다시 만드는 경로
  - E-07 실행 관찰 (2026-10-03, 기준 커밋의 개발 서버): REST 호출과 실제 브라우저 조작
  - E-08 기준선 테스트: backend 39건 통과, frontend 20건 통과
- Rejected evidence: 없음.
- Unresolved: 없음.

## Documents

- Summary: .omb/interview/2026-10-03-guardrail-toggle/summary.md
- Policy: .omb/interview/2026-10-03-guardrail-toggle/policy.md
- Development guide: .omb/interview/2026-10-03-guardrail-toggle/development-guide.md

## Acceptance record

Revision 1 을 2026-10-03 에 수락했다. 사용자 답변: "A 수락합니다."

## Next step

수락되면 `omb-goal` 파이프라인이 이 기록을 새 작업 브랜치로 옮겨 커밋하고, 그 브랜치의 PR 이 기록을
함께 담는다. 이후 계획 작성, 구현, 검증, 문서화, PR 생성까지 추가 질문 없이 진행한다.
