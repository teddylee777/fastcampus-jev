# 문서 기반 RAG 에 Jev 적용 — 변경 전용 개발 가이드

- Status: Accepted (2026-10-03)
- Revision: 1 (same reviewed revision as `policy.md` and `summary.md`)
- Interview summary: ./summary.md
- Full policy: [Complete policy](./policy.md)
- Applies to: `teddylee777/fastcampus-jev` 의 `main` 커밋 `e36edabb`. 이후 커밋에는 자동 적용되지 않는다
- Acceptance: Revision 1 accepted by the user on 2026-10-03

## 고정된 구현 기준선

| Repository / PR | Base ref and SHA | Head ref/repository and SHA | Merge-base / comparison SHA | Evidence limitations |
|---|---|---|---|---|
| teddylee777/fastcampus-jev, PR 없음 | `main` `e36edabb4f8b71c845c6ee67eb0ed47f9a313c3a` | 해당 없음 | 해당 없음 | 커밋되지 않은 `.claude/*.bak` 두 파일이 있으나 무관함 |

구현 전에 실제 체크아웃을 이 기준선과 비교한다. 관련 파일이 달라졌으면 해당 지시를 먼저 맞춘다.

## 필요한 변경과 순서

"제안/신규"로 표시한 경로와 이름은 아직 없는 것이다. 정책이 정한 동작을 바꾸지 않는 범위에서
구현자가 이름과 내부 구조를 조정할 수 있다.

| Task | Policy / behavior | Files / artifacts | Dependencies | Placement | Completion judgment |
|---|---|---|---|---|---|
| T-001 | P-011: PR 과 main push 에서 ruff, 오프라인 pytest, vitest 가 돈다 | `.github/workflows/ci.yml` (제안/신규) | 없음 | 단일 PR | PR 에 체크가 붙고 초록이다 |
| T-002 | P-001, P-002: 폴더로 나눈 문서 묶음과 결정적인 grep 검색기 | `jev_agent/rag/corpus/**` , `jev_agent/rag/corpus.py`, `jev_agent/rag/retriever.py`, `tests/test_rag_retriever.py` (모두 제안/신규) | 없음 | 단일 PR | 검색기 테스트 통과 |
| T-003 | P-003~P-008, P-012: Jev 판단 4종과 LLM 답변이 이어지는 그래프 | `jev_agent/rag/decisions.py`, `jev_agent/rag/graph.py`, `tests/test_rag_graph.py` (제안/신규), `langgraph.json` (수정) | T-002 | 단일 PR | S-001~S-009 테스트 통과 |
| T-004 | P-009: "문서 RAG" 탭 | `frontend/src/rag/RagTab.tsx`, `frontend/src/rag/RagTab.test.tsx` (제안/신규), `frontend/src/App.tsx`, `frontend/src/App.test.tsx` (수정) | T-003 | 단일 PR | vitest 통과, 탭이 메뉴에 보임 |
| T-005 | P-010: 12번 노트북 실제 실행과 README 갱신 | `scripts/build_notebooks.py` 또는 새 조각 모듈, `notebooks/12-*.ipynb`, `README.md` | T-003 | 단일 PR | 노트북에 실제 출력이 저장되고 설명의 숫자와 맞음 |

### T-001 — 최소 CI

- Outcome and policy reason: PR 에 체크가 붙어 자동 병합 조건이 성립한다 (P-011, D-002).
- Verified existing location: `.github/` 가 없다 (커밋 `e36edabb`). 테스트 명령은 `README.md:156-171`.
- Reproduce source: `git show e36edabb:README.md`
- Current behavior and gap: 워크플로가 없어 PR 체크가 0개다.
- Edit responsibilities: `.github/workflows/ci.yml` (제안/신규)을 만든다. `pull_request` 와 `main`
  push 에서 실행한다. 파이썬 작업은 `uv sync` 뒤 `uv run ruff check .` 와 오프라인 pytest 를,
  프론트엔드 작업은 `npm ci` 뒤 `npx vitest run` 을 돌린다. 비밀값을 쓰지 않는다.
- Conditions, order and failure results: pytest 는 `--timeout=10` 을 붙이고 작업에
  `timeout-minutes` 를 둔다. PR 감시는 `.github/**` 를 고칠 수 없으므로 첫 실행에서 초록이 되도록
  로컬에서 같은 명령을 먼저 돌려 본다.
- Target shape: pytest 대상은 `tests/` 아래 오프라인 테스트 전체다. 가짜 `OPENROUTER_API_KEY` 가
  필요한지는 구현 중 확인한다 (`jev_agent/jev.py:70-72` 는 키가 없으면 `JevError` 를 낸다).
- Documentation responsibility: T-005 의 README 갱신에서 CI 를 한 줄로 언급한다.
- Work order / dependencies: 없음.
- Placement decision: 단일 PR 에 포함. PR 없음 상태에서 새로 연다.

#### 검증과 완료

- Test location and cases: 워크플로 자체가 검증 대상이다.
- Run method: 로컬에서 `uv run ruff check .`, `uv run pytest tests/ -q --timeout=10`,
  `cd frontend && npx vitest run` 을 돌린다. 전체 스위트를 돌리는 이유는 CI 가 돌릴 명령과 같은지
  확인하기 위해서다.
- Pass criteria: 세 명령이 종료 코드 0 이고, PR 의 CI 체크가 초록이다.
- Verification status: planned

### T-002 — 문서 묶음과 grep 검색기

- Outcome and policy reason: Jev 가 설명만 보고 고를 수 있는 폴더 구조와, 선택된 파일에서 구절을
  찾는 결정적인 검색기 (P-001, P-002, D-005, D-006).
- Verified existing location: 검색 대상이 될 문서는 없다. 현재 비슷한 것은
  `jev_agent/tools.py:39` 의 `FAQ` 사전과 `tools.py:136-137` 의 `search_faq` 뿐이고, 이번에 바꾸지
  않는다.
- Reproduce source: `git show e36edabb:jev_agent/tools.py`
- Current behavior and gap: 폴더로 나뉜 문서와 파일 검색기가 없다.
- Edit responsibilities (모두 제안/신규):
  - `jev_agent/rag/corpus/<folder>/*.md`: 폴더 4~5개, 파일 10~12개. 각 파일은 첫 줄 `# 제목`,
    둘째 문단에 한 줄 요약, 그 아래 본문. 폴더마다 설명을 담는 `_folder.md` 를 둔다.
  - `jev_agent/rag/corpus.py`: 폴더와 파일 설명을 읽어 색인을 만든다. 설명이 빠진 항목은
    `ValueError` 로 알린다.
  - `jev_agent/rag/retriever.py`: 파일 목록과 질의를 받아 구절을 돌려준다.
- Conditions, order and failure results: 질의를 낱말로 나누고, 문단 단위로 낱말이 들어 있는 곳을
  찾아 일치한 낱말 수 순으로 정렬한다. 결과 수에 상한을 둔다. 일치가 없으면 빈 목록.
- Target shape:

  ```python
  class Passage(TypedDict):
      path: str        # corpus 기준 상대 경로
      line: int        # 문단 시작 줄
      text: str

  def load_corpus_index(root: Path) -> CorpusIndex: ...
  def search_passages(index: CorpusIndex, file_paths: list[str], query: str,
                      limit: int = 6) -> list[Passage]: ...
  ```

- Documentation responsibility: T-005 의 README 구성 표에 `jev_agent/rag/` 를 추가한다.
- Work order / dependencies: 없음.
- Placement decision: 단일 PR 에 포함.

#### 검증과 완료

- Test location and cases: `tests/test_rag_retriever.py` (제안/신규). 색인이 폴더와 파일 설명을
  모두 담는지, 설명이 없으면 오류인지, 일치하는 문단을 줄 번호와 함께 돌려주는지, 일치가 없으면
  빈 목록인지, 같은 입력에 같은 결과인지.
- Run method: `uv run pytest tests/test_rag_retriever.py -q --timeout=10`
- Pass criteria: 모든 케이스 통과.
- Verification status: planned

### T-003 — RAG 그래프

- Outcome and policy reason: 폴더 선택, 파일 선택, grep, 충분성, 답변, 근거 검증이 이어지는
  그래프 (P-003~P-008, P-012, D-004, D-007, D-008).
- Verified existing location (커밋 `e36edabb`):
  - 질문 빌더와 클라이언트: `jev_agent/jev.py:22-37`, `99-120`
  - 그래프 상태와 오류 처리 방식: `jev_agent/pattern_graphs.py:19-43`
  - 채팅 모델 생성: `jev_agent/agent.py:35-43` (`build_chat_model`)
  - 그래프 등록: `langgraph.json:3-10`
  - 가짜 Jev: `tests/test_patterns.py:15` (`ScriptedJev`)
- Reproduce source: `git show e36edabb:jev_agent/pattern_graphs.py`
- Current behavior and gap: RAG 그래프가 없다.
- Edit responsibilities:
  - `jev_agent/rag/decisions.py` (제안/신규): Jev 에 보낼 `state` 와 질문을 만드는 함수와, 답을
    해석하는 함수. 폴더 선택, 파일 선택, 충분성, 근거 검증 네 가지. 기준값은 모듈 상수.
  - `jev_agent/rag/graph.py` (제안/신규): 노드와 조건부 간선, `make_doc_rag` 진입점.
  - `langgraph.json` (수정): `graphs` 에 `"doc_rag": "./jev_agent/rag/graph.py:make_doc_rag"` 추가.
- Conditions, order and failure results:
  1. `select_folders`: `choice`, 옵션은 폴더 설명과 "해당 없음". 확률 0.25 이상을 최대 2개.
     없으면 종료 사유 `no_folder`.
  2. `select_files`: `choice`, 옵션은 선택된 폴더의 파일 요약과 "해당 없음". 확률 0.2 이상을
     최대 3개. 없으면 종료 사유 `no_file`.
  3. `search_passages`: T-002 의 검색기. 빈 결과면 종료 사유 `no_passage`.
  4. `judge_sufficiency`: `noul`. 0.5 미만이면 종료 사유 `insufficient`.
  5. `generate_answer`: LLM. 구절만 근거로 답한다.
  6. `verify_grounding`: `choice` (`supports`, `contradicts`, `says_nothing`).
  입력 검증 실패와 `JevError` 는 `error` 에 담는다. 반복 구간은 없다.
- Target shape:

  ```python
  # 입력: {"payload": {"query": str}}
  # 출력: {"output": {...}, "error": None} 또는 {"output": None, "error": str}
  output = {
      "status": "answered" | "no_folder" | "no_file" | "no_passage" | "insufficient",
      "steps": [  # 실행된 순서대로
          {"kind": "folder" | "file" | "sufficiency" | "grounding",
           "verdict": str, "probabilities": dict[str, float],
           "threshold": float | None, "latency_ms": int, "cost": float},
      ],
      "folders": list[str], "files": list[str], "passages": list[Passage],
      "answer": str | None,
      "grounding": "supports" | "contradicts" | "says_nothing" | None,
  }
  ```

  옵션 순서 편향을 줄이기 위해 폴더와 파일 옵션은 이름 순으로 고정하고 "해당 없음"을 마지막에
  둔다. 선택은 확률 값으로만 하고 순서에 기대지 않는다.
- Contract consumers: `langgraph.json` 의 기존 그래프 6개는 바뀌지 않는다. 새 그래프의 소비자는
  T-004 의 탭과 T-005 의 노트북이다.
- Documentation responsibility: T-005.
- Work order / dependencies: T-002 뒤.
- Placement decision: 단일 PR 에 포함.

#### 검증과 완료

- Test location and cases: `tests/test_rag_graph.py` (제안/신규). 가짜 Jev 와 가짜 LLM 으로
  S-001~S-009 를 각각 검증한다. 종료 분기에서는 LLM 이 불리지 않았음을 확인한다. 기준값 바로
  위와 아래의 확률로 경계를 확인한다. 옵션 순서를 바꿔도 선택이 같은지 확인한다.
- Run method: `uv run pytest tests/test_rag_graph.py -q --timeout=10`
- Pass criteria: 모든 케이스 통과. `uv run ruff check jev_agent/rag tests` 종료 코드 0.
- Verification status: planned

### T-004 — "문서 RAG" 탭

- Outcome and policy reason: 단계별 Jev 판단이 화면에 보인다 (P-009, D-004).
- Verified existing location (커밋 `e36edabb`):
  - 탭 구성: `frontend/src/App.tsx:10`, `86-94`
  - 그래프 호출: `frontend/src/lib/langgraph.ts:27-30` (`runPattern`)
  - 확률 막대: `frontend/src/components/ProbabilityBars.tsx`
- Reproduce source: `git show e36edabb:frontend/src/App.tsx`
- Current behavior and gap: 탭은 `PATTERNS` 설정에서만 만들어지고, `PatternTab` 은 Jev 호출 한
  번의 결과를 보여 주는 구조다.
- Edit responsibilities:
  - `frontend/src/rag/RagTab.tsx` (제안/신규): 질의 입력, 예시 선택, 단계별 결과 표시.
    `runPattern('doc_rag', { query })` 와 기존 `ProbabilityBars` 를 재사용한다.
  - `frontend/src/App.tsx` (수정): 메뉴에 "문서 RAG" 탭을 추가하고 `RagTab` 을 그린다.
- Conditions, order and failure results: 종료 사유별 안내 문구를 보여 준다. `grounding` 이
  `supports` 가 아니면 "근거 확인 필요" 표시. 서버 오류는 기존 탭과 같은 방식.
- Contract consumers: `runPattern` 의 시그니처는 바꾸지 않는다.
- Documentation responsibility: T-005 의 README 탭 표.
- Work order / dependencies: T-003 뒤.
- Placement decision: 단일 PR 에 포함.

#### 검증과 완료

- Test location and cases: `frontend/src/rag/RagTab.test.tsx` (제안/신규)에서 답변 표시, 종료
  사유 표시, 근거 확인 표시. `frontend/src/App.test.tsx` 에 탭 전환 케이스 추가.
- Run method: `cd frontend && npx vitest run src/rag/RagTab.test.tsx src/App.test.tsx`
- Pass criteria: 모든 케이스 통과. `npx tsc --noEmit` 종료 코드 0.
- Verification status: planned

### T-005 — 12번 노트북과 README

- Outcome and policy reason: 실제 출력이 담긴 노트북과 현재 상태에 맞는 README (P-010, D-009).
- Verified existing location (커밋 `e36edabb`):
  - 노트북 생성: `scripts/build_notebooks.py:1012` (`build`), 오픈소스편 조각은
    `scripts/notebooks_oss.py`
  - 노트북 실행: `scripts/run_notebooks.py:18` (`main`)
  - README: 구성 `README.md:11-28`, 목차 `30-61`, 탭 표 `105-112`, 테스트 `156-171`
- Reproduce source: `git show e36edabb:README.md`
- Current behavior and gap: 노트북은 00~11 까지이고 README 에 RAG 가 없다. 그래프 수가 6개로
  적혀 있다.
- Edit responsibilities:
  - 노트북 조각을 기존 생성 스크립트 방식으로 추가한다. 내용: 문서 구조, 폴더·파일 선택의 확률,
    기준값을 바꿔 보는 실험, 충분성으로 멈추는 사례, 근거 검증, 한계(문서 안 지시문, 점수의
    비반복성, 검색에서 놓친 것은 되살릴 수 없음).
  - `uv run python scripts/build_notebooks.py` 로 생성하고
    `uv run python scripts/run_notebooks.py 12` 로 실제 실행해 출력을 저장한다.
  - 실행 결과로 P-003, P-004, P-005 의 기준값을 조정했다면 `jev_agent/rag/decisions.py` 의 상수와
    테스트의 경계값을 함께 맞춘다.
  - `README.md` 의 구성, 목차, 탭 표, 그래프 수, 테스트 명령, 검증 상태 문단을 갱신한다.
- Conditions, order and failure results: 실제 실행에는 `.env` 의 `OPENROUTER_API_KEY` 와 선불
  크레딧이 필요하다. 없으면 출력 없는 노트북을 완료로 처리하지 않고 막힌 사유를 보고한다.
  웹 리서치의 수치를 본문에 쓸 때는 원문을 다시 확인한다.
- Target shape: Noul, Choice, probability, confidence 는 번역하지 않고 풀어서 설명한다.
- Documentation responsibility: 이 태스크 자체가 문서 작업이다.
- Work order / dependencies: T-003 뒤.
- Placement decision: 단일 PR 에 포함.

#### 검증과 완료

- Test location and cases: 자동 테스트 대상이 아니다. 실행된 노트북의 출력을 읽어 설명 글의
  숫자와 맞는지 확인한다.
- Run method: 위의 생성, 실행 명령. 기준값을 바꿨다면 T-003 의 테스트를 다시 돌린다.
- Pass criteria: `notebooks/12-*.ipynb` 의 모든 코드 셀에 출력이 있고 오류 출력이 없다. README 의
  노트북 수, 탭 수, 그래프 수가 실제와 맞다.
- Verification status: planned

## 남은 항목과 최종 승인

- 한국어에서의 Jev 확률 분포는 T-005 실행에서 확인한다. 영향 범위는 T-003 의 기준값 상수.
- Codex 앱 설치 여부는 로드맵 사전 점검에서 확인한다. 영향 범위는 PR 리뷰 단계.
- 승인 상태의 기준은 `summary.md` 의 frontmatter 이며 현재 사용자 검토를 기다린다.
