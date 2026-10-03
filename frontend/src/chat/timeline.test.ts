import type { Message } from '@langchain/langgraph-sdk'
import { describe, expect, it } from 'vitest'
import {
  buildTimeline,
  groupByTurn,
  hasAnswerStarted,
  stageLabel,
  totalLatencyMs,
  type JevDecision,
} from './timeline'

const human = (content: string): Message => ({ type: 'human', content, id: `h-${content}` })
const aiCall = (id: string, name: string, args: Record<string, unknown>): Message => ({
  type: 'ai',
  content: '',
  id: `ai-${id}`,
  tool_calls: [{ id, name, args, type: 'tool_call' }],
})
const toolResult = (callId: string, name: string, content: string): Message => ({
  type: 'tool',
  content,
  name,
  tool_call_id: callId,
  id: `tool-${callId}`,
})
const decision = (turn: number, latencyMs: number | null): JevDecision => ({
  kind: 'guardrail',
  title: '사용자 입력 검사',
  verdict: '통과',
  latency_ms: latencyMs,
  turn,
})

describe('buildTimeline', () => {
  it('should pair a tool call with its result as one item', () => {
    const timeline = buildTimeline([
      human('A1001 어디쯤이에요?'),
      aiCall('c1', 'track_shipping', { order_id: 'A1001' }),
      toolResult('c1', 'track_shipping', '옥천 허브 통과'),
      { type: 'ai', content: '내일 도착합니다.', id: 'ai-final' },
    ])

    expect(timeline.map((item) => item.kind)).toEqual(['human', 'tool', 'assistant'])
    expect(timeline[1]).toMatchObject({
      name: 'track_shipping',
      args: { order_id: 'A1001' },
      result: '옥천 허브 통과',
      status: 'done',
    })
  })

  it('should keep tool-call arguments visible even when the AI message has no text', () => {
    const timeline = buildTimeline([aiCall('c1', 'search_order', { order_id: 'A1002' })])

    expect(timeline).toHaveLength(1)
    expect(timeline[0]).toMatchObject({ kind: 'tool', status: 'running', result: null })
  })

  it('should mark a guardrail-blocked result and a refused call', () => {
    const timeline = buildTimeline([
      aiCall('c1', 'search_faq', { query: '쿠폰' }),
      toolResult('c1', 'search_faq', '[차단됨] 도구 결과에 지시문이 섞여 있어 내용을 제거했습니다.'),
      aiCall('c2', 'request_refund', { order_id: 'A1004' }),
      toolResult('c2', 'request_refund', '실행하지 않음: 담당자가 승인하지 않았습니다.'),
    ])

    expect(timeline.map((item) => (item.kind === 'tool' ? item.status : item.kind))).toEqual([
      'blocked',
      'refused',
    ])
  })

  it('should join text parts of structured content', () => {
    const timeline = buildTimeline([
      { type: 'ai', id: 'a', content: [{ type: 'text', text: '안녕' }, { type: 'text', text: '하세요' }] },
    ])

    expect(timeline[0]).toMatchObject({ kind: 'assistant', text: '안녕하세요' })
  })
})

describe('groupByTurn', () => {
  it('should group decisions by turn with the latest turn first', () => {
    const groups = groupByTurn([decision(1, 300), decision(1, 250), decision(2, 280)])

    expect(groups.map((group) => [group.turn, group.decisions.length])).toEqual([
      [2, 1],
      [1, 2],
    ])
  })

  it('should treat a decision without a turn as turn 1', () => {
    const { turn: _turn, ...legacy } = decision(1, 100)

    expect(groupByTurn([legacy])[0].turn).toBe(1)
  })
})

describe('totalLatencyMs', () => {
  it('should ignore decisions without a latency', () => {
    expect(totalLatencyMs([decision(1, 300), decision(1, null), decision(2, 200)])).toBe(500)
  })
})

describe('stageLabel', () => {
  const selected = (offered: string[]): JevDecision => ({
    kind: 'tool_select',
    title: '도구 선택',
    verdict: offered.join(', ') || '도구 없음',
    latency_ms: 250,
    turn: 1,
    offered,
  })

  it('should say the input is being checked before any decision arrives', () => {
    expect(stageLabel(buildTimeline([human('안녕')]), [])).toBe('입력을 검사하는 중')
  })

  it('should name the tool that is about to be called', () => {
    const timeline = buildTimeline([human('A1001 어디쯤?')])

    expect(stageLabel(timeline, [decision(1, 300), selected(['track_shipping'])])).toBe(
      'track_shipping 호출을 준비하는 중',
    )
  })

  it('should name a tool call that has no result yet', () => {
    const timeline = buildTimeline([human('A1001 어디쯤?'), aiCall('c1', 'track_shipping', {})])

    expect(stageLabel(timeline, [decision(1, 300)])).toBe('track_shipping 실행 중')
  })

  it('should ignore decisions from earlier turns', () => {
    const timeline = buildTimeline([
      human('첫 질문'),
      { type: 'ai', content: '답', id: 'a' },
      human('둘째 질문'),
    ])

    expect(stageLabel(timeline, [selected(['track_shipping'])])).toBe('입력을 검사하는 중')
  })

  const check = (title: string, verdict: string): JevDecision => ({
    kind: 'guardrail',
    title,
    verdict,
    latency_ms: null,
    turn: 1,
  })

  it('should say the request is being handled when the guardrail is off and no decision arrived', () => {
    expect(stageLabel(buildTimeline([human('안녕')]), [], false)).toBe('요청을 처리하는 중')
  })

  it('should say the guardrail is off after a skipped input check', () => {
    const decisions = [check('사용자 입력 검사', '꺼짐 → 검사 생략')]

    expect(stageLabel(buildTimeline([human('안녕')]), decisions, false)).toBe(
      '가드레일 꺼짐. 필요한 도구를 고르는 중',
    )
  })

  it('should say the guardrail is off after a skipped tool-output check', () => {
    const decisions = [check('도구 결과 검사: search_faq', '꺼짐 → 검사 생략')]

    expect(stageLabel(buildTimeline([human('안녕')]), decisions, false)).toBe(
      '가드레일 꺼짐. 다음 행동을 고르는 중',
    )
  })

  it('should keep the passed label after a passed input check', () => {
    const decisions = [check('사용자 입력 검사', '통과')]

    expect(stageLabel(buildTimeline([human('안녕')]), decisions)).toBe(
      '입력 검사 통과. 필요한 도구를 고르는 중',
    )
  })

  it('should follow the verdict of the record, not the switch', () => {
    const decisions = [check('사용자 입력 검사', '꺼짐 → 검사 생략')]

    expect(stageLabel(buildTimeline([human('안녕')]), decisions, true)).toBe(
      '가드레일 꺼짐. 필요한 도구를 고르는 중',
    )
  })
})

describe('hasAnswerStarted', () => {
  it('should be false while only the user message and tool calls exist', () => {
    expect(hasAnswerStarted(buildTimeline([human('q'), aiCall('c1', 'search_faq', {})]))).toBe(false)
  })

  it('should be true once assistant text follows', () => {
    expect(hasAnswerStarted(buildTimeline([human('q'), { type: 'ai', content: '답', id: 'a' }]))).toBe(true)
  })
})
