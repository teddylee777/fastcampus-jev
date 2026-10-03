import type { Message } from '@langchain/langgraph-sdk'

export type JevDecision = {
  kind: 'guardrail' | 'tool_select' | 'risk_gate'
  title: string
  verdict: string
  latency_ms: number | null
  turn?: number
  probabilities?: Record<string, number>
  thresholds?: Record<string, number>
  confidence?: number
  offered?: string[]
  detail?: string
}

export type ToolStatus = 'running' | 'done' | 'blocked' | 'refused'

export type TimelineItem =
  | { kind: 'human'; id: string; text: string }
  | { kind: 'assistant'; id: string; text: string }
  | {
      kind: 'tool'
      id: string
      name: string
      args: Record<string, unknown>
      result: string | null
      status: ToolStatus
    }

const BLOCKED_PREFIX = '[차단됨]'
const REFUSED_PREFIX = '실행하지 않음'
// 서버의 DISABLED_VERDICT(jev_agent/guardrails.py, '꺼짐 → 검사 생략')와 맞춘 접두어다.
const DISABLED_VERDICT_PREFIX = '꺼짐'

export function textOf(content: Message['content']): string {
  if (typeof content === 'string') return content
  return content.map((part) => ('text' in part ? part.text : '')).join('')
}

function statusOf(result: string | null): ToolStatus {
  if (result === null) return 'running'
  if (result.startsWith(BLOCKED_PREFIX)) return 'blocked'
  if (result.startsWith(REFUSED_PREFIX)) return 'refused'
  return 'done'
}

/** 메시지 목록을 화면 순서대로 정리한다. AI 의 도구 호출과 그 결과 메시지를 한 항목으로 묶는다. */
export function buildTimeline(messages: Message[]): TimelineItem[] {
  const resultByCallId = new Map<string, string>()
  for (const message of messages) {
    if (message.type === 'tool') resultByCallId.set(message.tool_call_id, textOf(message.content))
  }

  const timeline: TimelineItem[] = []
  messages.forEach((message, index) => {
    const id = message.id ?? `message-${index}`
    if (message.type === 'human') {
      timeline.push({ kind: 'human', id, text: textOf(message.content) })
      return
    }
    if (message.type !== 'ai') return // 도구 결과는 호출 카드 안에서 보여 준다.

    const text = textOf(message.content).trim()
    if (text) timeline.push({ kind: 'assistant', id, text })
    for (const call of message.tool_calls ?? []) {
      const callId = call.id ?? `${id}-${call.name}`
      const result = resultByCallId.get(callId) ?? null
      timeline.push({
        kind: 'tool',
        id: callId,
        name: call.name,
        args: call.args as Record<string, unknown>,
        result,
        status: statusOf(result),
      })
    }
  })
  return timeline
}

export type DecisionGroup = { turn: number; decisions: JevDecision[] }

/** 판단 기록을 대화 턴별로 묶는다. 최근 턴이 위에 온다. */
export function groupByTurn(decisions: JevDecision[]): DecisionGroup[] {
  const groups = new Map<number, JevDecision[]>()
  for (const decision of decisions) {
    const turn = decision.turn ?? 1
    groups.set(turn, [...(groups.get(turn) ?? []), decision])
  }
  return [...groups.entries()]
    .sort(([left], [right]) => right - left)
    .map(([turn, grouped]) => ({ turn, decisions: grouped }))
}

export function totalLatencyMs(decisions: JevDecision[]): number {
  return decisions.reduce((sum, decision) => sum + (decision.latency_ms ?? 0), 0)
}

/**
 * 답변 글자가 나오기 전까지 사용자에게 보여 줄 진행 상태.
 * 이번 턴에 쌓인 Jev 판단과 도구 호출에서 "지금 무엇을 하는 중인지"를 읽어 낸다.
 */
export function stageLabel(
  timeline: TimelineItem[],
  decisions: JevDecision[],
  isGuardrailEnabled = true,
): string {
  const turn = timeline.filter((item) => item.kind === 'human').length
  const running = timeline.findLast((item) => item.kind === 'tool' && item.status === 'running')
  if (running?.kind === 'tool') return `${running.name} 실행 중`

  const latest = decisions.filter((decision) => (decision.turn ?? 1) === turn).at(-1)
  if (!latest) return isGuardrailEnabled ? '입력을 검사하는 중' : '요청을 처리하는 중'
  if (latest.kind === 'guardrail') {
    const isSkipped = latest.verdict.startsWith(DISABLED_VERDICT_PREFIX)
    if (latest.title.startsWith('도구 결과')) {
      return isSkipped ? '가드레일 꺼짐. 다음 행동을 고르는 중' : '도구 결과를 확인했습니다. 다음 행동을 고르는 중'
    }
    return isSkipped ? '가드레일 꺼짐. 필요한 도구를 고르는 중' : '입력 검사 통과. 필요한 도구를 고르는 중'
  }
  if (latest.kind === 'tool_select') {
    return latest.offered?.length ? `${latest.offered.join(', ')} 호출을 준비하는 중` : '답변을 작성하는 중'
  }
  return '도구를 실행하는 중'
}

/** 마지막 사용자 메시지 뒤에 답변 글자가 이미 나오기 시작했는지. */
export function hasAnswerStarted(timeline: TimelineItem[]): boolean {
  return timeline.at(-1)?.kind === 'assistant'
}
