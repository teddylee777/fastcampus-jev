import { Client } from '@langchain/langgraph-sdk'

export const API_URL: string = import.meta.env.VITE_LANGGRAPH_URL ?? 'http://localhost:2024'

const client = new Client({ apiUrl: API_URL })

export type PatternStat = { label: string; value: string | number }
export type PatternRow = {
  title: string
  verdict: string
  tone: 'good' | 'warn' | 'bad' | 'neutral'
  probabilities: Record<string, number>
  thresholds: Record<string, number>
  body: string
}
export type PatternOutput = {
  stats: PatternStat[]
  rows: PatternRow[]
  latency_ms: number
  cost: number
}

type GraphState<TOutput> = { output?: TOutput | null; error?: string | null }

/**
 * 그래프를 한 번 실행하고 결과를 돌려준다. Jev 호출은 서버에서만 일어난다.
 * `isOutput` 을 주면 서버 응답의 모양을 확인하고, 맞지 않으면 화면에 닿기 전에 reject 한다.
 */
export async function runGraph<TOutput>(
  graphId: string,
  payload: Record<string, unknown>,
  isOutput?: (value: unknown) => value is TOutput,
): Promise<TOutput> {
  const state = (await client.runs.wait(null, graphId, { input: { payload } })) as GraphState<unknown>
  if (state.error) throw new Error(state.error)
  if (!state.output) throw new Error('서버가 결과를 돌려주지 않았습니다.')
  if (isOutput && !isOutput(state.output)) throw new Error('서버 응답 모양이 올바르지 않습니다.')
  return state.output as TOutput
}

/** 패턴 그래프를 한 번 실행하고 결과를 돌려준다. */
export function runPattern(graphId: string, payload: Record<string, unknown>): Promise<PatternOutput> {
  return runGraph<PatternOutput>(graphId, payload)
}
