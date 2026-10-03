# 문서 기반 RAG 에 Jev 적용 — 전체 정책

- Status: Accepted (2026-10-03)
- Revision: 1 (mirrors `revision` in `summary.md`)
- Interview summary: ./summary.md
- Scope: 문서 RAG 기능 전체 (문서 묶음, 검색기, RAG 그래프, 탭, 노트북, CI, 전달 방식)
- Development guide: [Change-only guide](./development-guide.md)
- Supersedes/relates to: 관련 ADR 없음
- Acceptance: Revision 1 accepted by the user on 2026-10-03

## 목적과 개념

이 저장소는 판단 전용 모델 Jev 를 에이전트에 붙이는 방법을 가르치는 세미나 자료다. 지금까지는
도구 선택, 가드레일, 위험 게이트, 메모리 압축, 검색 라우팅을 다뤘고, 문서를 실제로 찾아와 답하는
RAG 는 없었다. 이 기능은 "문서를 찾고 답하는 과정에서 Jev 가 어디를 맡으면 좋은가"를 실제로 도는
예제로 보여 준다.

핵심 개념은 역할 분리다. Jev 는 글을 쓰지 못하므로 어디서 찾을지, 찾은 것으로 답할 수 있는지, 쓴
답이 문서에 근거하는지를 판단한다. 문서 본문을 찾는 일은 grep 이, 답변을 쓰는 일은 LLM 이 맡는다.

성공 기준:

- 문서에 답이 있는 질의는 올바른 폴더와 파일을 거쳐 근거가 표시된 답을 낸다.
- 문서에 답이 없는 질의는 지어내지 않고 "문서에서 찾지 못했다"로 끝난다.
- 각 Jev 판단의 확률이 화면과 노트북에 보인다.
- 테스트는 네트워크 없이 돈다.

## 대표 흐름

```text
질의
  └▶ 폴더 선택 (Jev choice)        해당 없음 → "문서에 없는 내용"으로 종료     P-003
      └▶ 파일 선택 (Jev choice)    해당 없음 → "문서에 없는 내용"으로 종료     P-004
          └▶ grep (코드)           선택된 파일에서 질의 낱말이 든 구절 수집    P-002
              └▶ 충분성 (Jev noul) 부족 → "문서에서 찾지 못했습니다"로 종료    P-005
                  └▶ 답변 생성 (LLM) 구절만 근거로 답을 작성                  P-006
                      └▶ 근거 검증 (Jev choice) 답이 구절에 근거하는지 표시   P-007
```

Jev 호출은 질의 하나에 최대 4번이다. 앞 단계에서 종료되면 뒤 호출은 일어나지 않는다.

## 범위와 경계

포함: 문서 묶음과 설명, grep 검색기, RAG 그래프, 전용 탭, 12번 노트북, README, 최소 CI.

제외와 이유:

- chunk 별 관련도 판정: `jev_agent/patterns/routing.py` 의 `rel_N` 판정과 겹친다.
- 문서 안 인젝션 판정: `jev_agent/guardrails.py` 에 같은 질문이 있다. 이 기능에서는 시스템
  프롬프트로만 다루고, 그 한계를 노트북에 적는다.
- 임베딩, 벡터 저장소, BM25: 사용자가 파일 기반 grep 으로 시작하기로 했다.
- 고객지원 에이전트 연동, 캐스케이드, 질의 재작성 루프: 이번 범위가 아니다.

요구 영역별 상태:

| 영역 | 상태 |
|---|---|
| 문서 구조와 검색 | 정의됨 (P-001, P-002) |
| Jev 판단과 기준값 | 정의됨. 기준값은 시작값이며 실제 실행으로 조정 (P-003, P-004, P-005, P-007) |
| 실패와 오류 처리 | 정의됨 (P-008) |
| 화면 | 정의됨 (P-009) |
| 테스트와 CI | 정의됨 (P-011, P-012) |
| 권한, 데이터 수명 주기 | 해당 없음. 문서는 저장소에 포함된 읽기 전용 예제이고 사용자 데이터를 저장하지 않는다 |

## 조사 기준선과 출처 권위

| Source/repository | Fixed revision or observation | Location | What it establishes | Authority / limitations |
|---|---|---|---|---|
| teddylee777/fastcampus-jev | `e36edabb4f8b71c845c6ee67eb0ed47f9a313c3a` (main) | `jev_agent/jev.py:22-37`, `99-120` | 질문 빌더 `choice`, `noul`, `score` 와 `JevClient.decide`, `adecide` | 구현 근거 |
| 같은 저장소 | 같은 커밋 | `jev_agent/patterns/routing.py:40-41`, `77-80` | 검색 결과별 관련도 `rel_N` 판정이 이미 있음 | 구현 근거 |
| 같은 저장소 | 같은 커밋 | `jev_agent/patterns/__init__.py:18-23` | 패턴 등록 사전 `PATTERNS` 와 `plan`/`view` 계약 | 구현 근거 |
| 같은 저장소 | 같은 커밋 | `jev_agent/pattern_graphs.py:19-43` | `PatternState`(`payload`, `output`, `error`)와 노드 하나짜리 그래프 | 구현 근거 |
| 같은 저장소 | 같은 커밋 | `langgraph.json:3-10` | 서버에 등록된 그래프 6개 | 구현 근거 |
| 같은 저장소 | 같은 커밋 | `frontend/src/App.tsx:86-94`, `frontend/src/lib/langgraph.ts:27-30` | 탭이 `PATTERNS` 설정에서 만들어지고 `runs.wait` 로 그래프를 부름 | 구현 근거 |
| 같은 저장소 | 같은 커밋 | `pyproject.toml:5-19` | 벡터 저장소, 임베딩 의존성이 없음 | 구현 근거 |
| 같은 저장소 | 같은 커밋 | `README.md:156-171` | 오프라인 테스트 명령 | 문서 근거 |
| 같은 저장소 | 같은 커밋 | `.github/` 없음 | CI 워크플로가 없음 | 부재를 확인함 |
| TypeSafe cookbook | 2026-10-03 열람 | https://docs.typesafe.ai/cookbooks/ (`classifying_rag_passages`, `semantic_find`, `citation_check`, `parallel_questions`) | passage 판정, 충분성 `noul`, 근거 `choice`, 질문 묶음 호출 | 벤더 문서. 요약 도구로 읽어 문구와 수치가 원문과 다를 수 있음 |
| TypeSafe 한계 문서 | 2026-10-03 열람 | https://docs.typesafe.ai/model-jaggedness/jev-1.13.md | `choice` 의 첫 옵션 편향, 산술·날짜 약점, 지시문을 적대적으로 보지 않음 | 같은 제한 |
| 커뮤니티 PR | 2026-10-03 열람 | https://github.com/krutikpatel/ragAppWithExperiments/pull/22 | 같은 입력에서도 점수가 달라짐 | 단일 사례 |

작업 트리에는 커밋되지 않은 `.claude/settings.json.bak`, `.claude/settings.local.json.bak` 두 파일이
있다. 로컬 설정 백업이며 이 기능과 무관하다.

## 전체 정책

### P-001 — 문서 묶음 구조

- Rule: RAG 대상 문서는 저장소에 포함된 `.md` 파일이다. 주제별 폴더로 나누고, 폴더마다 한 줄
  설명을, 파일마다 제목과 한 줄 요약을 둔다. Jev 는 폴더와 파일을 고를 때 본문이 아니라 이 설명을
  읽는다.
- Defaults, limits and applicability: 폴더 4~5개, 파일 10~12개 규모의 간단한 임의 문서. 주제는 기존
  예제와 맞춰 쇼핑몰 '테디마켓' 운영 안내로 한다. 두 폴더에 걸치는 주제를 하나 이상, 어느 문서에도
  답이 없는 질의 예시를 하나 이상 둔다.
- Exceptions and failures: 설명이 없는 폴더나 파일은 색인을 만들 때 오류로 알린다. 조용히
  건너뛰지 않는다.
- Related rules: P-003, P-004
- Provenance: 회의 결정 D-006, D-005
- Key reason and decision: 사용자가 "간단하게 임의의 `.md` 파일"과 "폴더 구조를 잘 잡을 것"을
  지시했다. 폴더가 주제로 갈려야 Jev 의 폴더 선택이 의미를 갖는다.

### P-002 — 파일 기반 grep 검색기

- Rule: 검색기는 선택된 파일 안에서 질의의 낱말이 들어 있는 구절을 찾아 파일 경로, 줄 번호와 함께
  돌려준다. 네트워크와 외부 서비스를 쓰지 않으며 같은 입력에는 항상 같은 결과를 낸다.
- Defaults, limits and applicability: 구절 단위는 문단이다. 돌려주는 구절 수에 상한을 둔다.
  새 런타임 의존성은 추가하지 않는다.
- Exceptions and failures: 맞는 구절이 하나도 없으면 빈 목록을 돌려준다. 이 경우 충분성 판단 없이
  "문서에서 찾지 못했습니다"로 끝낸다 (P-005).
- Related rules: P-004, P-005
- Provenance: 회의 결정 D-005
- Key reason and decision: 사용자가 파일 기반 grep 으로 먼저 시작하기로 했다. 결과가 결정적이어서
  테스트와 CI 에서 그대로 검증된다.

### P-003 — Jev 의 폴더 선택

- Rule: 질의와 폴더 설명을 Jev 에 보내 `choice` 로 폴더를 고른다. 옵션에 "해당 없음"을 넣는다.
  확률이 기준값 이상인 폴더를 확률 순으로 최대 2개까지 고른다.
- Exceptions and failures: 1등이 "해당 없음"이거나 기준값을 넘는 폴더가 없으면 검색하지 않고
  "문서에 없는 내용"으로 끝낸다.
- Defaults, limits and applicability: 기준값의 시작값은 0.25 다. 한국어 실제 호출 결과를 보고
  조정한다. 옵션 수는 `choice` 한도(255개)보다 훨씬 작다.
- Related rules: P-001, P-004, P-012
- Provenance: 회의 결정 D-005, D-008
- Key reason and decision: `choice` 는 맞는 것이 없어도 하나를 고르므로 "해당 없음"이 필요하다.
  두 폴더에 걸치는 질의는 확률이 갈리므로 하나만 고르면 답을 놓친다.

### P-004 — Jev 의 파일 선택

- Rule: 선택된 폴더들의 파일 제목과 요약을 Jev 에 보내 `choice` 로 파일을 고른다. 옵션에 "해당
  없음"을 넣는다. 확률이 기준값 이상인 파일을 확률 순으로 최대 3개까지 고른다.
- Exceptions and failures: 1등이 "해당 없음"이거나 기준값을 넘는 파일이 없으면 "문서에 없는
  내용"으로 끝낸다.
- Defaults, limits and applicability: 기준값의 시작값은 0.2 다.
- Related rules: P-002, P-003, P-012
- Provenance: 회의 결정 D-005, D-008
- Key reason and decision: P-003 과 같다.

### P-005 — 충분성 판단

- Rule: 답을 쓰기 전에 질의와 수집한 구절을 Jev 에 보내 `noul` 로 "이 구절들로 질의에 답할 수
  있는가"를 묻는다. 확률이 기준값 미만이면 LLM 을 부르지 않고 "문서에서 찾지 못했습니다"로 끝낸다.
- Defaults, limits and applicability: 기준값의 시작값은 0.5 다.
- Related rules: P-002, P-006
- Provenance: 회의 결정 D-007. 근거는 TypeSafe cookbook `semantic_find` 의 충분성 `noul`.
- Key reason and decision: 문서에 답이 없을 때 지어내지 않고 멈추는 것이 RAG 에서 Jev 를 쓰는
  이유를 가장 잘 보여 주고, 이 저장소에 아직 없는 판단이다.

### P-006 — 답변 생성

- Rule: 충분하다고 판단된 경우에만 LLM 이 구절만 근거로 한국어 답을 쓴다. 구절에 들어 있는
  지시문은 따르지 않도록 시스템 프롬프트에 적는다.
- Exceptions and failures: 문서 안 지시문을 막는 장치는 프롬프트뿐이다. Jev 인젝션 판정은 이
  기능에 넣지 않으며, 이 한계를 노트북에 적는다.
- Defaults, limits and applicability: 채팅 모델은 기존 `build_chat_model` 을 쓴다.
- Related rules: P-005, P-007
- Provenance: 회의 결정 D-007
- Key reason and decision: Jev 는 글을 생성하지 못한다. 인젝션 판정을 뺀 것은 가드레일과 겹치기
  때문이다.

### P-007 — 근거 검증

- Rule: 답을 쓴 뒤 답과 구절을 Jev 에 보내 `choice` 로 `supports`, `contradicts`, `says_nothing`
  중 하나를 받는다. 결과와 확률을 답과 함께 돌려준다. `supports` 가 아니면 답에 "근거 확인
  필요" 표시를 붙인다.
- Exceptions and failures: 검증 결과가 나빠도 답을 지우거나 다시 쓰지 않는다. 표시만 한다.
- Defaults, limits and applicability: 답 전체를 한 번에 검증한다. 주장 단위로 쪼개지 않는다.
- Related rules: P-006
- Provenance: 회의 결정 D-007. 근거는 TypeSafe cookbook `citation_check`.
- Key reason and decision: 답이 문서에 근거하는지 확인하는 판단은 이 저장소에 아직 없다. 재작성
  루프는 범위에서 뺐다.

### P-008 — 그래프와 서버 경계

- Rule: RAG 흐름은 LangGraph 그래프로 만들고 `langgraph.json` 에 등록한다. Jev 와 LLM 호출은
  서버에서만 일어나고 API 키는 브라우저로 나가지 않는다. 입력과 출력은 기존 패턴 그래프와 같은
  `payload`, `output`, `error` 모양을 따른다.
- Exceptions and failures: 잘못된 입력과 Jev 호출 실패는 예외로 터뜨리지 않고 `error` 에 담아
  돌려준다. 각 단계의 Jev 판단은 `output` 에 순서대로 남긴다.
- Defaults, limits and applicability: 그래프에 반복 구간은 없다. 종료 분기는 조건부 간선으로
  드러낸다.
- Related rules: P-003~P-007, P-009
- Provenance: 회의 결정 D-004. 기존 방식은 `jev_agent/pattern_graphs.py:19-43`.
- Key reason and decision: 분기가 있는 흐름이라 그래프가 맞고, 기존 등록 방식을 그대로 따른다.

### P-009 — 프론트엔드 탭

- Rule: 왼쪽 메뉴에 "문서 RAG" 탭을 추가한다. 질의를 넣으면 폴더 확률, 선택된 파일, 찾은 구절,
  충분성, 답변, 근거 검증 결과를 단계 순서대로 보여 준다. 예시 질의를 고를 수 있다.
- Exceptions and failures: 중간에 종료된 경우 어느 단계에서 왜 멈췄는지 보여 준다. 서버 오류는
  기존 탭과 같은 방식으로 표시한다.
- Defaults, limits and applicability: 예시는 정상, 두 폴더에 걸침, 문서에 없음 세 가지를 둔다.
- Related rules: P-008
- Provenance: 회의 결정 D-004
- Key reason and decision: 기존 패턴 탭은 Jev 호출 한 번의 결과를 보여 주는 구조라 여러 단계
  흐름에는 전용 화면이 필요하다.

### P-010 — 노트북과 README

- Rule: 12번 노트북을 `scripts/build_notebooks.py` 방식으로 생성하고 실제 Jev API 와 채팅 모델로
  실행해 출력을 저장한다. 설명 글의 숫자는 저장된 출력과 맞춘다. README 의 구성, 목차, 탭 표,
  그래프 수, 테스트 명령을 갱신한다.
- Exceptions and failures: 실행 시점에 API 키나 크레딧이 없으면 그 사실을 보고하고 출력 없는
  노트북을 완료로 처리하지 않는다.
- Defaults, limits and applicability: 노트북에서 기준값을 바꿔 보는 실험과 한계(문서 안 지시문,
  점수의 비반복성)를 다룬다. 용어 Noul, Choice, probability, confidence 는 번역하지 않는다.
- Related rules: P-003~P-007
- Provenance: 회의 결정 D-009, D-004. 용어 규칙은 사용자의 기존 지침.
- Key reason and decision: 기존 노트북이 모두 실제 출력을 담고 있어 12번만 비면 일관성이 깨진다.

### P-011 — 최소 CI

- Rule: PR 과 `main` push 에서 ruff, 오프라인 pytest, 프론트엔드 vitest 를 돌리는 GitHub Actions
  워크플로를 둔다. 실제 API 를 부르지 않는다.
- Defaults, limits and applicability: pytest 는 `--timeout=10` 을 붙이고 작업에 제한 시간을 둔다.
- Exceptions and failures: PR 감시는 `.github/**` 를 고칠 수 없다. 워크플로 자체가 깨지면 사람이
  고쳐야 한다.
- Related rules: P-012, P-013
- Provenance: 회의 결정 D-002
- Key reason and decision: CI 체크가 0개인 PR 은 기본 설정에서 자동 병합 조건을 만족하지 못한다.

### P-012 — 테스트 방침

- Rule: 새 코드는 가짜 Jev 와 가짜 LLM 으로 네트워크 없이 검증한다. 확률을 다루는 검증은 정확한
  값이 아니라 기준값의 위아래로 한다. 폴더·파일 선택은 옵션 순서를 바꿔도 결과가 같음을 테스트로
  확인한다.
- Related rules: P-003, P-004, P-011
- Provenance: 유지되는 기존 방침(`README.md:156-171`)과 회의 중 반영하기로 한 조사 결과.
- Key reason and decision: Jev 점수는 실행마다 달라지고 `choice` 는 첫 옵션으로 기우는 경향이
  보고되어 있다.

### P-013 — 전달 방식

- Rule: 전체를 단위 하나, PR 하나로 구현한다. 구현은 Claude 가 하고 Codex 는 PR 리뷰어로만 쓴다.
  CI 가 초록이고 리뷰 지적이 처리되면 자동 병합한다.
- Exceptions and failures: 병합 게이트가 거절하면 PR 은 사람의 병합을 기다린다. Codex 앱이
  설치되어 있지 않으면 리뷰 대기가 시간 초과로 끝난다.
- Defaults, limits and applicability: 대상 저장소는 `teddylee777/fastcampus-jev`, 기준 브랜치는
  `main` 이다.
- Related rules: P-011
- Provenance: 회의 결정 D-001, D-003, D-009, D-010
- Key reason and decision: 사용자가 한 번에 전부 구현하고 노트북도 자동 병합하기로 했다.

## 상황과 기대 결과

| Scenario | Policy | Kind | Initial conditions and action | Expected observable outcome |
|---|---|---|---|---|
| S-001 | P-003~P-007 | Normal | 문서에 답이 있는 질의 | 폴더와 파일이 선택되고 구절이 수집되며, 답과 `supports` 결과가 나온다 |
| S-002 | P-003, P-004 | Normal | 두 폴더에 걸치는 질의 | 폴더 2개가 선택되고 양쪽 파일이 grep 대상이 된다 |
| S-003 | P-003 | Exception | 문서와 무관한 질의 | 폴더 선택에서 "해당 없음"으로 끝나고 grep 과 LLM 호출이 없다 |
| S-004 | P-002, P-005 | Exception | 폴더와 파일은 골랐지만 맞는 구절이 없는 질의 | "문서에서 찾지 못했습니다"로 끝나고 LLM 호출이 없다 |
| S-005 | P-005 | Exception | 구절은 있지만 충분성 확률이 기준값 미만 | "문서에서 찾지 못했습니다"로 끝나고 LLM 호출이 없다 |
| S-006 | P-007 | Exception | 답이 구절과 어긋남 | 답은 유지되고 "근거 확인 필요" 표시와 판정 확률이 붙는다 |
| S-007 | P-008 | Prohibited | 질의가 비어 있는 입력 | `error` 에 사유가 담기고 Jev 호출이 없다 |
| S-008 | P-008 | Exception | Jev 호출이 실패 | 예외 없이 `error` 에 사유가 담긴다 |
| S-009 | P-012 | Normal | 같은 질의에서 폴더 옵션 순서만 바꿈 | 선택 결과가 같다 |

## 전체 정책 구현 비교

판정 범위는 커밋 `e36edabb` 의 소스 열람이다. 테스트 실행 결과가 아니다.

| Policy | Judgment | Frozen evidence and judgment scope | Required action |
|---|---|---|---|
| P-001, P-002 | 불일치 | 문서 묶음과 검색기가 없다. `jev_agent/tools.py:39` 의 `FAQ` 사전과 `search_faq` 만 있다 | T-002 |
| P-003~P-008 | 불일치 | RAG 그래프가 없다. `langgraph.json:3-10` 에 그래프 6개만 있다. 질문 빌더와 클라이언트(`jev_agent/jev.py:22-37`, `99-120`)는 이미 있어 재사용한다 | T-003 |
| P-009 | 불일치 | `frontend/src/patterns/config.ts` 에 RAG 탭이 없다 | T-004 |
| P-010 | 불일치 | 노트북은 00~11 까지 있고 README 에 RAG 항목이 없다 | T-005 |
| P-011 | 불일치 | `.github/` 디렉터리가 없다 | T-001 |
| P-012 | 충족 (기존 코드 범위) | `tests/test_patterns.py:15` 의 `ScriptedJev` 등 가짜 Jev 로 도는 테스트가 있다. 새 코드에 대한 테스트는 각 태스크에 포함 | T-002~T-004 에서 새 테스트 추가 |
| P-013 | 충족 (전제 조건 범위) | `origin/main` 이 `e36edabb` 를 가리킨다. Codex 앱 설치 여부는 확인하지 못함 | 로드맵 사전 점검에서 확인 |

## 결정과 근거

| Decision | Issue / previous direction and evidence | Adopted policy and reason | Rejected alternatives and reasons / verified history | Affected areas |
|---|---|---|---|---|
| D-001 | 인터뷰 시작 시 로컬에 커밋이 없고 원격이 비어 있었다 | 첫 커밋을 `origin/main` 에 올리는 데 사용자가 동의했다. 확인 시점에 `e36edabb` 가 이미 올라가 있어 추가 작업은 없었다 | 직접 push 하는 안, PR 방식을 쓰지 않는 안 | P-013 |
| D-002 | `.github/` 가 없어 PR 체크가 0개 | 최소 CI 추가. 이미 있는 오프라인 테스트를 그대로 쓴다 | 체크 없이 병합 허용: 검증 없는 병합이 된다. 수동 병합: 자동화 목적과 어긋난다 | P-011, T-001 |
| D-003 | `--codex` 는 ultra-goal 이 해석하지 않는 옵션 | Codex 를 리뷰어로만 쓴다. PR 감시에 리뷰 요청 절차가 이미 있다 | 구현까지 위임: 단위 실행에 기본 경로가 없다. 사용 안 함 | P-013 |
| D-004 | 앱에는 채팅 에이전트와 패턴 탭 두 자리가 있다 | 실제로 도는 RAG 그래프와 전용 탭, 노트북. 충분성과 근거 검증은 검색과 생성이 이어져야 보인다 | 패턴 탭만: 라우팅 탭과 겹친다. 고객지원 에이전트까지: 범위와 회귀 위험이 크다 | P-008~P-010, T-003~T-005 |
| D-005 | 의존성에 검색 도구가 없다. 추천안은 BM25 였다 | 사용자 지시로 파일 기반 grep. 폴더 구조를 잘 잡고 폴더·파일 선택을 Jev 가 한다 | BM25, 임베딩, 둘의 결합 | P-001~P-004, T-002, T-003 |
| D-006 | 대상 문서가 없다 | 사용자 지시로 간단한 `.md` 를 임의 생성. 주제와 규모는 진행자의 가정(테디마켓, 10~12개) | 저장소 자체를 문서로, 사용자의 실제 문서 | P-001, T-002 |
| D-007 | 검색 이후 판단 지점 네 가지가 조사됨 | 충분성과 근거 검증만 넣는다 | 최소 구성: 잘못 고른 파일을 막지 못한다. 전체 구성: 기존 탭, 가드레일과 겹친다 | P-005~P-007, T-003 |
| D-008 | 폴더를 잘못 고르면 뒤에서 되살릴 수 없다 | 확률 기준으로 폴더 최대 2개, 파일 최대 3개. "해당 없음"이면 종료 | 1등 하나만. LLM 캐스케이드 추가: 03번 노트북과 겹친다 | P-003, P-004, T-003 |
| D-009 | 노트북은 실제 API 실행 출력을 담는 것이 기존 방식 | 실제 실행 후 자동 병합. 추천안은 병합 전 확인이었으나 사용자가 자동 병합을 골랐다 | 생성까지만, 병합 전 확인 | P-010, T-005 |
| D-010 | 추천안은 PR 5개였다 | 사용자 지시로 한 번에 전부 구현. 단위 하나, PR 하나 | 5개, 3개로 나누는 안 | P-013, T-001~T-005 |

## 남은 근거와 결정

정책 결정으로 남은 것은 없다. 다음 세 가지는 구현 중 확인한다.

- 한국어 질의에서의 Jev 확률 분포. P-003, P-004, P-005 의 기준값이 시작값인 이유다.
- Codex GitHub 앱 설치 여부.
- 웹 리서치 수치의 원문 대조.

## 최종 검토와 승인

세 문서의 D-ID, P-ID, T-ID 가 서로 맞는지 확인했다. 불일치 판정은 모두 개발 가이드의 태스크로
이어진다. 승인 상태의 기준은 `summary.md` 의 frontmatter 이며, 현재는 사용자 검토를 기다린다.
문서 승인은 구현 완료를 뜻하지 않는다.
