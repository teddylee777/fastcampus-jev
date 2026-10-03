import { beforeEach, describe, expect, it, vi } from 'vitest'
import { runGraph, runPattern, type PatternOutput } from './langgraph'

const runsWait = vi.hoisted(() => vi.fn())

vi.mock('@langchain/langgraph-sdk', () => ({
  Client: class {
    runs = { wait: runsWait }
  },
}))

const patternOutput: PatternOutput = {
  stats: [{ label: '판단', value: 'A' }],
  rows: [],
  latency_ms: 120,
  cost: 0.00001,
}

type Echo = { echo: string }
const isEcho = (value: unknown): value is Echo =>
  typeof value === 'object' && value !== null && typeof (value as Echo).echo === 'string'

beforeEach(() => {
  runsWait.mockReset()
})

describe('runPattern', () => {
  it('should call runs.wait with the payload and return the output', async () => {
    runsWait.mockResolvedValue({ output: patternOutput, error: null })

    const output = await runPattern('memory_compaction', { text: '안녕' })

    expect(runsWait).toHaveBeenCalledTimes(1)
    expect(runsWait).toHaveBeenCalledWith(null, 'memory_compaction', {
      input: { payload: { text: '안녕' } },
    })
    expect(output).toEqual(patternOutput)
  })

  it('should throw the server error', async () => {
    runsWait.mockResolvedValue({ output: null, error: 'Jev 호출이 실패했습니다.' })

    await expect(runPattern('memory_compaction', {})).rejects.toThrow('Jev 호출이 실패했습니다.')
  })

  it('should throw when the output is empty', async () => {
    runsWait.mockResolvedValue({ output: null, error: null })

    await expect(runPattern('memory_compaction', {})).rejects.toThrow('서버가 결과를 돌려주지 않았습니다.')
  })
})

describe('runGraph', () => {
  it('should return the output', async () => {
    runsWait.mockResolvedValue({ output: { echo: 'hello' }, error: null })

    const output = await runGraph<Echo>('doc_rag', { query: 'q' }, isEcho)

    expect(runsWait).toHaveBeenCalledWith(null, 'doc_rag', { input: { payload: { query: 'q' } } })
    expect(output).toEqual({ echo: 'hello' })
  })

  it('should throw on error', async () => {
    runsWait.mockResolvedValue({ output: null, error: '402 Payment Required' })

    await expect(runGraph('doc_rag', { query: 'q' })).rejects.toThrow('402 Payment Required')
  })

  it('should throw on empty output', async () => {
    runsWait.mockResolvedValue({ output: null, error: null })

    await expect(runGraph('doc_rag', { query: 'q' })).rejects.toThrow('서버가 결과를 돌려주지 않았습니다.')
  })

  it('should throw when the guard rejects the output', async () => {
    runsWait.mockResolvedValue({ output: { echo: 42 }, error: null })

    await expect(runGraph<Echo>('doc_rag', { query: 'q' }, isEcho)).rejects.toThrow(
      '서버 응답 모양이 올바르지 않습니다.',
    )
  })
})
