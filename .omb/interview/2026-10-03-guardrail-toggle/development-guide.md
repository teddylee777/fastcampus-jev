# 가드레일 켜기/끄기 스위치 — 변경 전용 개발 가이드

- Status: Accepted
- Revision: 1 (`policy.md`, `summary.md` 와 같은 리비전)
- Interview summary: ./summary.md
- Full policy: [전체 정책](./policy.md)
- Applies to: 저장소 `fastcampus-jev`, 커밋 `bb1bccd4163738353de70f3b5510146fce3f0052`. 이후 커밋은 검토하지 않았다.
- Acceptance: Revision 1 accepted on 2026-10-03 ("A 수락합니다.")

## 고정 구현 기준선

| Repository / PR | Base ref and SHA | Head ref and SHA | Merge-base | Evidence limitations |
|---|---|---|---|---|
| `fastcampus-jev`, PR 없음 | 해당 없음 | `main` `bb1bccd4163738353de70f3b5510146fce3f0052` | 해당 없음 | 추적되지 않는 `lecture/`, `.claude/settings*.json.bak` 만 있다. 이 주제와 무관하다 |

구현 전에 실제 체크아웃을 이 기준선과 비교한다. 관련 파일이 달라졌다면 해당 지시를 먼저 맞춘다.

기준선 테스트 실행 결과(2026-10-03, 기준 커밋):

- 저장소 루트에서 `uv run pytest tests/test_jev_agent.py -q --timeout=10` → 39 passed.
- `frontend/` 에서 `npx vitest run src/chat/timeline.test.ts src/App.test.tsx` → 20 passed.

## 필요한 변경과 순서

| Task | Policy / behavior | Files / artifacts | Dependencies | Placement | Completion judgment |
|---|---|---|---|---|---|
| T-001 | P-003, P-004. 위험 도구의 결과도 스위치에 따라 검사되거나 "검사 생략"으로 기록된다 | `jev_agent/guardrails.py`, `jev_agent/middleware.py`, `jev_agent/agent.py`, `tests/test_jev_agent.py` | 없음 | PR 없음. 이번 작업 브랜치 | 새 테스트와 기존 39건 통과, S-003~S-007 |
| T-002 | P-005. 꺼짐 상태의 진행 문구가 검사했다고 말하지 않는다 | `frontend/src/chat/timeline.ts`, `frontend/src/chat/ChatTab.tsx`, `frontend/src/chat/timeline.test.ts` | 없음 | 같은 브랜치 | 새 테스트와 기존 테스트 통과, S-008~S-010 |
| T-003 | P-006. 꺼짐 상태의 예시 힌트가 "가드레일 꺼짐: 검사 생략"이다 | `frontend/src/chat/ChatTab.tsx`, `frontend/src/chat/ChatTab.test.tsx` (새 파일), `README.md` | T-002 (같은 파일 `ChatTab.tsx` 를 고친다) | 같은 브랜치 | 새 테스트 통과, S-011, README 반영 |
| T-004 | P-003, P-005, P-006. 실제 화면에서 세 결함이 사라졌는지 확인한다 | 실행 기록 | T-001, T-002, T-003 | 같은 브랜치 | 아래 절차의 관찰 결과가 기대와 같다 |

### T-001 — 위험 도구의 결과도 가드레일 검사를 받는다

- Outcome and policy reason: P-003, P-004, D-001, D-002. 실행된 `cancel_order`, `request_refund` 의
  결과가 켜짐이면 검사되고 꺼짐이면 "꺼짐 → 검사 생략"으로 기록된다.
- Verified existing location (커밋 `bb1bccd4163738353de70f3b5510146fce3f0052`):
  - `jev_agent/guardrails.py:82-86` `TOOL_BLOCKED_TEXT`
  - `jev_agent/guardrails.py:170-177` `JevGuardrailMiddleware.__init__`
  - `jev_agent/guardrails.py:262-312` `_output_verdict`, `_pass_through`, `wrap_tool_call`, `awrap_tool_call`
  - `jev_agent/middleware.py:281-294` `JevRiskGateMiddleware._refusal`, `_with_entry`
  - `jev_agent/agent.py:56-60` 미들웨어 목록
  - `jev_agent/tools.py:162` `RISKY_TOOLS`
- Reproduce source: `git show bb1bccd4163738353de70f3b5510146fce3f0052:jev_agent/guardrails.py`
- Current behavior and gap: 가드레일이 가장 바깥 미들웨어라 `handler(request)` 의 반환값은 위험 게이트를
  거친 값이다. 위험 게이트는 실행 결과와 거절을 모두 `Command(update={"messages": [ToolMessage],
  "jev_decisions": [게이트 기록]})` 로 돌려준다. 가드레일은 `isinstance(output, ToolMessage)` 가 아니면
  바로 반환하므로(`guardrails.py:290-291, 303-304`) 위험 도구 결과는 검사도 기록도 없다.
- Edit responsibilities:
  - `jev_agent/middleware.py`: 거절 접두어 `"실행하지 않음"` 을 모듈 상수 `REFUSAL_PREFIX` (proposed/new)로
    빼고 `_refusal` 이 그 상수로 문장을 만든다. 문장 내용은 바뀌지 않는다.
  - `jev_agent/guardrails.py`:
    - 상수 `RISKY_TOOL_BLOCKED_TEXT` (proposed/new)를 추가한다. 값은 정책 P-004 의 위험 도구 문구와 글자
      하나까지 같다.
    - `JevGuardrailMiddleware.__init__` 에 키워드 인자 `irreversible_tools: tuple[str, ...] = ()`
      (proposed/new)를 추가한다. 이 목록에 든 도구의 결과가 차단되면 `RISKY_TOOL_BLOCKED_TEXT` 를 쓴다.
    - `wrap_tool_call`, `awrap_tool_call` 이 `Command` 결과를 풀어 본다. 동기와 비동기 경로가 같은
      판정 함수를 쓴다.
    - `_output_verdict`, `_pass_through` 가 이미 있던 판단 기록을 보존한다.
  - `jev_agent/agent.py`: `JevGuardrailMiddleware(jev, irreversible_tools=RISKY_TOOLS)` 로 바꾼다.
    미들웨어 순서는 바꾸지 않는다. 순서를 바꾸면 위험 게이트의 `_with_entry` 가 가드레일의 `Command` 를
    받아 자기 기록을 잃는다.
- Conditions, order and failure results:
  1. `handler` 결과가 `ToolMessage` 면 지금과 같다.
  2. 결과가 `Command` 이고 `update` 가 dict 이며 `update["messages"]` 가 `ToolMessage` 하나만 든 목록이면
     그 메시지를 꺼낸다. 그 밖의 형태는 손대지 않고 그대로 반환한다.
  3. 꺼낸 메시지의 내용이 `REFUSAL_PREFIX` 로 시작하면 원래 `Command` 를 그대로 반환한다. Jev 를 부르지
     않고 기록도 추가하지 않는다.
  4. 스위치가 꺼져 있으면 메시지를 그대로 두고 "꺼짐 → 검사 생략" 기록을 추가한다.
  5. 켜져 있으면 Jev 로 검사한다. 차단 판정이거나 `JevError` 면 내용을 차단 문구로 바꾼다.
     도구 이름이 `irreversible_tools` 에 있으면 `RISKY_TOOL_BLOCKED_TEXT`, 아니면 `TOOL_BLOCKED_TEXT` 다.
  6. 반환하는 `Command` 의 `jev_decisions` 는 `[*원래 기록, 도구 결과 검사 기록]` 순서다. `update` 의
     다른 키는 보존한다. `stamp_turn` 으로 턴 번호를 적는다.
- Target shape:

  ```python
  def _unwrap(output: Any) -> tuple[ToolMessage | None, list[dict[str, Any]]]:
      """(검사할 도구 메시지, 안쪽 미들웨어가 남긴 판단 기록). 검사 대상이 아니면 (None, [])."""
      if isinstance(output, ToolMessage):
          return output, []
      update = output.update if isinstance(output, Command) else None
      messages = update.get("messages") if isinstance(update, dict) else None
      if not (isinstance(messages, list) and len(messages) == 1):
          return None, []
      message = messages[0]
      if not isinstance(message, ToolMessage) or str(message.content).startswith(REFUSAL_PREFIX):
          return None, []
      return message, list(update.get("jev_decisions", []))
  ```

  헬퍼의 이름과 위치는 구현자가 정해도 된다. 위 여섯 단계의 결과가 같아야 한다.
- Contract consumers:
  - `frontend/src/chat/timeline.ts:30-31, 38-43` 은 `[차단됨]`, `실행하지 않음` 접두어로 카드 상태를
    정한다. 두 접두어가 그대로이므로 수정이 필요 없다.
  - `tests/test_jev_agent.py:441-512` 의 위험 게이트 테스트는 판정 문자열, 주문 상태, 기록 종류의 집합,
    마지막 기록의 턴 번호만 본다. 도구 결과 검사 기록이 하나 늘어도 단언이 깨지지 않을 것으로 예상하지만
    실행으로 확인한다.
  - `scripts/build_notebooks.py:617` 과 `notebooks/04-가드레일.ipynb` 는 `JevGuardrailMiddleware(jev)` 를
    위치 인자 하나로 부른다. 새 인자에 기본값이 있어 수정이 필요 없다. 그 밖의 호출부는
    `jev_agent/agent.py:57` 뿐이다 (`git grep "JevGuardrailMiddleware("` 로 확인).
- Documentation responsibility: `jev_agent/guardrails.py` 모듈 docstring 의 조치 표 아래에 위험 도구
  결과도 인젝션 검사를 받는다는 한 문장을 더한다. README 는 T-003 에서 다룬다.
- Work order / dependencies: 없음. 실패하는 테스트를 먼저 쓴다.
- Placement decision: PR 없음. 이번 작업 브랜치에서 처리한다.

#### 검증과 완료

- Test location and cases: `tests/test_jev_agent.py` 에 추가한다 (모두 proposed).
  1. `test_guardrail_checks_risky_tool_output_after_the_gate` — `FakeJev(tool=REFUND_TOOL, requested=0.97)`,
     "A1002 불량이라 환불해 주세요". 기록에 제목 "도구 결과 검사: request_refund", 판정 "통과"가 있고
     `risk_gate` 기록 바로 뒤에 온다. 주문 상태는 환불접수 (S-003).
  2. `test_guardrail_disabled_records_skip_for_risky_tool_output` — 같은 요청에
     `{"configurable": {"guardrail_enabled": False}}`. 판정은 "꺼짐 → 검사 생략", 도구 메시지는 원문 (S-004).
  3. `test_guardrail_does_not_check_gate_refusals` — `requested=0.03`. 도구 메시지는 "실행하지 않음"으로
     시작하고, 도구 결과 검사 기록이 없으며, 질문이 `injection` 하나뿐인 Jev 호출이 없다 (S-005).
  4. `test_guardrail_replaces_flagged_risky_tool_output_with_executed_notice` — `injection` 을 상태가 도구
     결과 문자열일 때만 0.99 를 돌려주는 함수로 준다. 도구 메시지는 `RISKY_TOOL_BLOCKED_TEXT`, 주문 상태는
     환불접수 (S-006).
  5. `test_guardrail_blocks_risky_tool_output_when_jev_fails` — `injection` 함수가 도구 결과에 대해
     `JevError` 를 던진다. 도구 메시지는 `RISKY_TOOL_BLOCKED_TEXT`, 판정은 "Jev 호출 실패 → 차단" (S-007).
  6. `test_async_path_checks_risky_tool_output` — `ainvoke` 로 1번과 같은 단언.
- Run method: 저장소 루트에서 `uv run pytest tests/test_jev_agent.py -q --timeout=10`. 린트는
  `uv run ruff check jev_agent tests` (ruff 는 `pyproject.toml` 의 dev 그룹에 있고, 이 회의에서는 실행하지 않았다).
- Pass criteria: 새 테스트 6건이 수정 전에 실패하고 수정 후 통과한다. 기존 39건이 모두 통과한다.
- Verification status: planned. 예상하는 RED 는 아직 관찰한 결과가 아니다.

### T-002 — 꺼짐 상태의 진행 문구

- Outcome and policy reason: P-005, D-001.
- Verified existing location: `frontend/src/chat/timeline.ts:101-115` `stageLabel`,
  `frontend/src/chat/ChatTab.tsx:187` 호출부, `frontend/src/chat/timeline.test.ts:105-142` 기존 테스트.
- Reproduce source: `git show bb1bccd4163738353de70f3b5510146fce3f0052:frontend/src/chat/timeline.ts`
- Current behavior and gap: 기록이 없으면 항상 "입력을 검사하는 중", 최근 기록이 가드레일이면 판정과
  무관하게 "입력 검사 통과…" 또는 "도구 결과를 확인했습니다…"를 돌려준다.
- Edit responsibilities:
  - `timeline.ts`: `stageLabel(timeline, decisions, isGuardrailEnabled = true)` 로 세 번째 인자를 더한다.
    기본값이 `true` 라 기존 호출과 기존 테스트 네 건은 그대로 유효하다. 꺼짐 판정 접두어 `'꺼짐'` 은
    모듈 상수로 둔다.
  - `ChatTab.tsx:187`: `stageLabel(timeline, decisions, isGuardrailEnabled)` 로 바꾼다.
- Target shape: 정책 P-005 의 표와 글자 하나까지 같은 문자열을 돌려준다. 기록이 없는 행은 세 번째 인자로,
  나머지 두 행은 `latest.verdict.startsWith('꺼짐')` 으로 고른다.
- Contract consumers: `stageLabel` 의 호출부는 `ChatTab.tsx:187` 과 `timeline.test.ts` 뿐이다
  (`grep -rn stageLabel frontend/src` 로 확인).
- Work order / dependencies: 없음.
- Placement decision: 같은 브랜치.

#### 검증과 완료

- Test location and cases: `frontend/src/chat/timeline.test.ts` 의 `describe('stageLabel')` 에 추가한다 (proposed).
  1. 기록 없음, 세 번째 인자 `false` → "요청을 처리하는 중" (S-008).
  2. 최근 기록이 제목 "사용자 입력 검사", 판정 "꺼짐 → 검사 생략" → "가드레일 꺼짐. 필요한 도구를 고르는 중" (S-009).
  3. 최근 기록이 제목 "도구 결과 검사: search_faq", 판정 "꺼짐 → 검사 생략" → "가드레일 꺼짐. 다음 행동을 고르는 중" (S-010).
  4. 최근 기록이 제목 "사용자 입력 검사", 판정 "통과" → "입력 검사 통과. 필요한 도구를 고르는 중" (켜짐 열 회귀).
- Run method: `frontend/` 에서 `npx vitest run src/chat/timeline.test.ts`. 타입과 린트는 `npx tsc -b`,
  `npm run lint` (`frontend/package.json` 의 스크립트이고, 이 회의에서는 실행하지 않았다).
- Pass criteria: 새 테스트 1~3 이 수정 전에 실패하고 수정 후 통과한다. 기존 `stageLabel` 테스트 네 건이 통과한다.
- Verification status: planned.

### T-003 — 꺼짐 상태의 예시 힌트와 README

- Outcome and policy reason: P-006, D-001.
- Verified existing location: `frontend/src/chat/ChatTab.tsx:20-44` `EXAMPLES`, `:145-152` 예시 카드 렌더링,
  `README.md:104-111` 예시 카드 표.
- Current behavior and gap: 힌트가 고정 문자열이라 꺼짐 상태에서도 "가드레일: 차단" 등으로 나온다.
- Edit responsibilities:
  - `ChatTab.tsx`: 가드레일 예시 네 개(쿠폰 문의, 프롬프트 인젝션, 개인정보 포함, 거친 표현)에 표식을
    달고, 스위치가 꺼져 있으면 그 예시의 힌트 자리에 `가드레일 꺼짐: 검사 생략` 을 보여 준다. 문구는 모듈
    상수로 둔다. 나머지 세 예시와 예시 본문은 바꾸지 않는다.
  - `README.md`: 예시 카드 표(`:104-111`) 바로 아래에 스위치 설명 한 문단을 더한다. 내용은 다음 네 가지다.
    상단의 가드레일 스위치를 끄면 입력과 도구 결과 검사를 건너뛰고 패널에 "꺼짐 → 검사 생략"이 남는다.
    스위치를 꺼도 LLM 이 스스로 거절할 수 있다. 환불과 취소 결과도 검사 대상이다. 새 대화와 새로고침은
    스위치를 켜짐으로 되돌린다.
- Contract consumers: `frontend/src/App.test.tsx` 의 `useStream` 모의 객체는 메시지를 돌려주므로 예시
  카드가 그려지지 않는다. 이 파일은 수정하지 않는다.
- Work order / dependencies: T-002 뒤에 한다. 같은 파일을 고친다.
- Placement decision: 같은 브랜치.

#### 검증과 완료

- Test location and cases: `frontend/src/chat/ChatTab.test.tsx` (proposed/new). `@langchain/langgraph-sdk/react`
  의 `useStream` 을 메시지가 빈 상태로 모의한다.
  1. 처음에는 "가드레일: 차단" 힌트가 보이고 "가드레일 꺼짐: 검사 생략"은 없다.
  2. 스위치를 누르면 "가드레일 꺼짐: 검사 생략"이 네 번 보이고 "도구 선택", "위험 게이트 자동 승인",
     "사람 확인 요청" 힌트는 그대로다 (S-011).
  3. 다시 누르면 1번 상태로 돌아온다.
- Run method: `frontend/` 에서 `npx vitest run src/chat/ChatTab.test.tsx src/App.test.tsx`.
- Pass criteria: 2번이 수정 전에 실패하고 수정 후 통과한다. `App.test.tsx` 가 통과한다. README 문단이 네
  가지 내용을 담는다.
- Verification status: planned.

### T-004 — 실제 화면에서 확인

- Outcome and policy reason: P-003, P-005, P-006. 단위 테스트는 실제 서버 스트림과 화면의 조합을 증명하지
  못한다.
- Edit responsibilities: 코드 변경 없음. 확인 절차만 수행하고 결과를 기록한다.
- Conditions: 이미 떠 있는 개발 서버(2024, 5173)는 기본 체크아웃의 코드를 쓴다. 작업 브랜치의 코드를 보려면
  작업 디렉터리에서 서버를 다른 포트로 띄운다. 예: 작업 디렉터리 루트에서
  `uv run langgraph dev --port 2025 --no-browser`, `frontend/` 에서
  `VITE_LANGGRAPH_URL=http://localhost:2025 npx vite --port 5174`. `.env` 는 추적되지 않으므로 작업
  디렉터리에 있는지 먼저 확인한다. 없으면 이 과업은 실행 불가로 기록하고 사유를 적는다.
- Work order / dependencies: T-001, T-002, T-003 뒤.

#### 검증과 완료

- Inputs and expected outcomes (`frontend/scripts/guardrail-shots.mjs` 처럼 `@playwright/test` 의 chromium 으로 조작한다):
  1. 빈 대화에서 스위치를 끈다 → 네 예시의 힌트가 "가드레일 꺼짐: 검사 생략".
  2. 꺼짐 상태로 "A1002 불량이라 환불해 주세요" 전송 → 진행 문구에 "입력을 검사하는 중"과 "입력 검사
     통과"가 한 번도 나오지 않는다. 패널에 "도구 결과 검사: request_refund / 꺼짐 → 검사 생략"이 있다.
  3. 스위치를 켜고 새 대화에서 같은 문장 전송 → 패널에 "도구 결과 검사: request_refund / 통과"가 있다.
  4. 브라우저 콘솔 오류가 0건이다.
- Run method: 검증된 자동 실행기는 없다. 위 순서를 Playwright 스크립트로 한 번 실행하고 출력을 기록한다.
  스크립트는 임시 파일로 두고 커밋하지 않는다.
- Pass criteria: 네 항목의 관찰이 모두 기대와 같다.
- Verification status: planned.

## 남은 항목과 최종 수락

남은 결정이나 증거는 없다. 수락 여부의 기준은 `summary.md` 의 frontmatter 다. Revision 1 이 2026-10-03 에 수락됐다.
