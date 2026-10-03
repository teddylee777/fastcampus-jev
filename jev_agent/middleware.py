"""Jev 를 DeepAgents(LangChain 미들웨어)에 끼워 넣는 미들웨어: 도구 선택과 위험 도구 게이트.

가드레일 미들웨어는 jev_agent/guardrails.py 에 있다.

역할 분담이 핵심이다.
- Jev: 빠르고 싼 판단 (어떤 도구? 공격인가? 실행해도 되는가?)
- LLM: 도구 인자 채우기와 답변 문장 생성

각 미들웨어는 판단 결과를 state 의 `jev_decisions` 에 쌓는다. 프론트엔드는 이 값을 읽어
probability 막대를 그린다.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, NotRequired

from langchain.agents.middleware import AgentMiddleware, AgentState, ExtendedModelResponse
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.types import Command, interrupt

from jev_agent.jev import JevClient, JevError, JevResult, choice, noul

NO_TOOL = "no_tool"
# 위험 게이트가 거절한 도구 메시지의 접두어. 화면의 도구 카드 상태와 가드레일이 이 값을 기준으로 삼는다.
REFUSAL_PREFIX = "실행하지 않음"


class JevState(AgentState):
    """에이전트 state 에 Jev 판단 기록을 추가한다."""

    jev_decisions: NotRequired[Annotated[list[dict[str, Any]], operator.add]]


def last_user_text(messages: list[Any]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


def called_tool_names(messages: list[Any]) -> list[str]:
    """마지막 사용자 메시지 이후에 이미 실행된 도구 이름. Jev 에게는 결과 원문 대신 이것만 준다."""
    names: list[str] = []
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            break
        if isinstance(message, ToolMessage) and message.name:
            names.append(message.name)
    return list(reversed(names))


def turn_index(messages: list[Any]) -> int:
    """지금까지 들어온 사용자 메시지 수. 판단 기록을 대화 턴별로 묶는 데 쓴다."""
    return sum(1 for message in messages if isinstance(message, HumanMessage))


def stamp_turn(update: Any, messages: list[Any]) -> Any:
    """state 업데이트(dict 또는 Command)에 담긴 판단 기록에 턴 번호를 적는다."""
    payload = update.update if isinstance(update, Command) else update
    if isinstance(payload, dict):
        for entry in payload.get("jev_decisions", []):
            entry["turn"] = turn_index(messages)
    return update


def record(kind: str, title: str, verdict: str, result: JevResult | None, **extra: Any) -> dict:
    """프론트엔드 패널에 보여줄 판단 기록 한 건."""
    return {
        "kind": kind,
        "title": title,
        "verdict": verdict,
        "latency_ms": round(result.latency_ms) if result else None,
        **extra,
    }


# --- 2. 도구 선택: Jev 가 후보를 좁히고 LLM 이 인자를 채운다 --------------------
class JevToolSelectorMiddleware(AgentMiddleware):
    """모델 호출 직전에 Jev choice 질문으로 필요한 도구를 고른다.

    confidence 가 높으면 probability 가 min_probability 이상인 상위 top_k 개만 LLM 에 노출하고(System 1),
    confidence 가 낮으면 전체 도구를 그대로 넘겨 LLM 이 고르게 한다(System 2 로 캐스케이드).
    """

    state_schema = JevState

    def __init__(
        self,
        jev: JevClient,
        catalog: dict[str, str],
        top_k: int = 2,
        min_confidence: float = 0.5,
        min_probability: float = 0.1,
        hide_builtin_tools: bool = False,
    ) -> None:
        super().__init__()
        self.jev = jev
        self.catalog = catalog
        self.top_k = top_k
        self.min_confidence = min_confidence
        # 상위 top_k 안에 들어도 이 probability 보다 낮은 도구는 LLM 에 보여 주지 않는다.
        self.min_probability = min_probability
        # True 면 catalog 에 없는 도구(Deep Agents 내장 ls, grep, read_file 등)를 LLM 에 보여 주지 않는다.
        # 고객지원 봇은 파일 도구를 쓸 일이 없고, 보이면 LLM 이 가끔 엉뚱하게 호출한다.
        self.hide_builtin_tools = hide_builtin_tools

    def _question(self) -> dict[str, dict[str, Any]]:
        options = {
            **self.catalog,
            NO_TOOL: "도구가 필요 없다. 인사, 잡담이거나 필요한 도구가 이미 모두 실행되었다.",
        }
        return {
            "tool": choice(
                "사용자 요청을 처리하기 위해 지금 다음으로 실행해야 할 도구는 무엇인가?", options
            )
        }

    @staticmethod
    def _jev_state(request: Any) -> dict[str, Any]:
        return {
            "user_request": last_user_text(request.messages),
            "already_called_tools": called_tool_names(request.messages),
        }

    def _is_builtin_visible(self, tool: Any) -> bool:
        return getattr(tool, "name", None) in self.catalog or not self.hide_builtin_tools

    def _delegate_all(self, request: Any) -> Any:
        """Jev 가 고르지 못했을 때: catalog 도구 전부를 LLM 에 맡긴다."""
        if not self.hide_builtin_tools:
            return request
        return request.override(tools=[t for t in request.tools if self._is_builtin_visible(t)])

    def _narrow(self, request: Any, result: JevResult | None) -> tuple[Any, dict[str, Any]]:
        if result is None:
            entry = record("tool_select", "도구 선택", "Jev 실패 → LLM 에 전체 위임", None)
            return self._delegate_all(request), entry
        answer = result["tool"]
        confidence = answer.get("confidence", 0.0)
        probabilities = answer.get("probabilities", {})
        if confidence < self.min_confidence:
            entry = record(
                "tool_select",
                "도구 선택",
                "확신 낮음 → LLM 에 전체 위임",
                result,
                probabilities=probabilities,
                confidence=confidence,
            )
            return self._delegate_all(request), entry
        ranked = sorted(probabilities, key=probabilities.get, reverse=True)[: self.top_k]
        allowed = {
            name
            for name in ranked
            if name != NO_TOOL and probabilities[name] >= self.min_probability
        }
        # Jev 가 관리하는 도구(catalog)만 걸러 낸다. 내장 도구는 hide_builtin_tools 설정을 따른다.
        tools = [
            t
            for t in request.tools
            if (
                t.name in allowed
                if getattr(t, "name", None) in self.catalog
                else self._is_builtin_visible(t)
            )
        ]
        entry = record(
            "tool_select",
            "도구 선택",
            ", ".join(sorted(allowed)) or "도구 없음",
            result,
            probabilities=probabilities,
            confidence=confidence,
            offered=sorted(allowed),
        )
        return request.override(tools=tools), entry

    def wrap_model_call(self, request: Any, handler: Any) -> Any:
        try:
            result = self.jev.decide(self._jev_state(request), self._question())
        except JevError:
            result = None
        narrowed, entry = self._narrow(request, result)
        entry["turn"] = turn_index(request.messages)
        response = handler(narrowed)
        return ExtendedModelResponse(
            model_response=response, command=Command(update={"jev_decisions": [entry]})
        )

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        try:
            result = await self.jev.adecide(self._jev_state(request), self._question())
        except JevError:
            result = None
        narrowed, entry = self._narrow(request, result)
        entry["turn"] = turn_index(request.messages)
        response = await handler(narrowed)
        return ExtendedModelResponse(
            model_response=response, command=Command(update={"jev_decisions": [entry]})
        )


# --- 3. 위험 도구 게이트: confidence 기반 캐스케이드 --------------------------------
class JevRiskGateMiddleware(AgentMiddleware):
    """되돌릴 수 없는 도구를 실행하기 전에 Jev 에게 '사용자가 명시적으로 요청했는가'를 묻는다.

    probability >= approve_above  → 바로 실행 (기본 0.93)
    probability <= block_below    → 실행하지 않고 거절 메시지 반환
    그 사이(애매함)        → interrupt() 로 사람에게 넘긴다
    """

    state_schema = JevState

    def __init__(
        self,
        jev: JevClient,
        risky_tools: tuple[str, ...],
        approve_above: float = 0.93,
        block_below: float = 0.15,
    ) -> None:
        super().__init__()
        self.jev = jev
        self.risky_tools = risky_tools
        self.approve_above = approve_above
        self.block_below = block_below

    @staticmethod
    def _question() -> dict[str, dict[str, Any]]:
        return {
            "requested": noul(
                "사용자가 이 주문에 대해 이 작업을 실행해 달라고 직접, 명확하게 요청했는가?",
                true="사용자가 같은 주문 번호와 같은 작업을 분명히 요청했다.",
                false="사용자는 조회나 문의만 했거나, 다른 주문/다른 작업을 말했다.",
            )
        }

    @staticmethod
    def _jev_state(request: Any) -> dict[str, Any]:
        return {
            "user_request": last_user_text(request.state["messages"]),
            "proposed_action": request.tool_call["name"],
            "arguments": request.tool_call["args"],
        }

    def _decide_action(self, request: Any, result: JevResult | None) -> tuple[str, dict[str, Any]]:
        """'run' | 'block' | 'ask' 중 하나와 판단 기록을 돌려준다."""
        name = request.tool_call["name"]
        if result is None:
            return "ask", record(
                "risk_gate", f"위험 도구 게이트: {name}", "Jev 실패 → 사람 확인", None
            )
        probability = result["requested"]["noul"]
        if probability >= self.approve_above:
            action, verdict = "run", "자동 승인"
        elif probability <= self.block_below:
            action, verdict = "block", "차단"
        else:
            action, verdict = "ask", "애매함 → 사람 확인"
        entry = record(
            "risk_gate",
            f"위험 도구 게이트: {name}",
            verdict,
            result,
            probabilities={"requested": probability, "not_requested": 1 - probability},
            thresholds={"requested": self.approve_above},
        )
        return action, entry

    @staticmethod
    def _ask_human(request: Any, entry: dict[str, Any]) -> bool:
        # interrupt() 앞의 코드는 재개할 때 다시 실행된다. Jev 판단은 부작용이 없어 다시 실행돼도 안전하다.
        answer = interrupt(
            {
                "type": "approval_request",
                "tool": request.tool_call["name"],
                "args": request.tool_call["args"],
                "jev": entry,
            }
        )
        return bool(answer.get("approved")) if isinstance(answer, dict) else bool(answer)

    @staticmethod
    def _refusal(request: Any, entry: dict[str, Any], reason: str) -> Command:
        message = ToolMessage(
            content=f"{REFUSAL_PREFIX}: {reason}",
            name=request.tool_call["name"],
            tool_call_id=request.tool_call["id"],
        )
        return Command(update={"messages": [message], "jev_decisions": [entry]})

    @staticmethod
    def _with_entry(output: Any, entry: dict[str, Any]) -> Any:
        if isinstance(output, ToolMessage):
            return Command(update={"messages": [output], "jev_decisions": [entry]})
        return output

    def wrap_tool_call(self, request: Any, handler: Any) -> Any:
        if request.tool_call["name"] not in self.risky_tools:
            return handler(request)
        try:
            result = self.jev.decide(self._jev_state(request), self._question())
        except JevError:
            result = None
        action, entry = self._decide_action(request, result)
        entry["turn"] = turn_index(request.state["messages"])
        if action == "block":
            return self._refusal(request, entry, "사용자가 요청하지 않은 작업으로 판단했습니다.")
        if action == "ask" and not self._ask_human(request, entry):
            return self._refusal(request, entry, "담당자가 승인하지 않았습니다.")
        return self._with_entry(handler(request), entry)

    async def awrap_tool_call(self, request: Any, handler: Any) -> Any:
        if request.tool_call["name"] not in self.risky_tools:
            return await handler(request)
        try:
            result = await self.jev.adecide(self._jev_state(request), self._question())
        except JevError:
            result = None
        action, entry = self._decide_action(request, result)
        entry["turn"] = turn_index(request.state["messages"])
        if action == "block":
            return self._refusal(request, entry, "사용자가 요청하지 않은 작업으로 판단했습니다.")
        if action == "ask" and not self._ask_human(request, entry):
            return self._refusal(request, entry, "담당자가 승인하지 않았습니다.")
        return self._with_entry(await handler(request), entry)
