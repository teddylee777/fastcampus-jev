import { describe, expect, it } from 'vitest'
import { isRagOutput, isRagStatus, type RagOutput } from './types'

const answered: RagOutput = {
  status: 'answered',
  steps: [
    {
      kind: 'folder',
      verdict: 'shipping',
      selected: ['shipping'],
      labels: {},
      probabilities: { shipping: 0.91, none: 0.04 },
      threshold: 0.25,
      latency_ms: 210,
      cost: 0.00001,
    },
    {
      kind: 'file',
      verdict: 'shipping/delivery_fee.md',
      selected: ['shipping/delivery_fee.md'],
      labels: { 'shipping/delivery_fee.md': '배송비 안내', none__shipping: '해당 없음 (shipping)' },
      probabilities: { 'shipping/delivery_fee.md': 0.88, none__shipping: 0.02 },
      threshold: 0.2,
      latency_ms: 190,
      cost: 0.00001,
    },
    {
      kind: 'grounding',
      verdict: 'supports',
      selected: ['supports'],
      labels: {},
      probabilities: { supports: 0.9, contradicts: 0.02, says_nothing: 0.08 },
      threshold: null,
      latency_ms: 180,
      cost: 0.00001,
    },
  ],
  folders: ['shipping'],
  files: ['shipping/delivery_fee.md'],
  passages: [{ path: 'shipping/delivery_fee.md', line: 3, text: '배송비는 3,000원입니다.' }],
  answer: '배송비는 3,000원입니다.',
  grounding: 'supports',
}

type Json = Record<string, unknown>

function withStep(patch: Json): Json {
  return { ...answered, steps: [{ ...answered.steps[0], ...patch }] }
}

describe('isRagStatus', () => {
  it('should accept the five contract statuses and reject anything else', () => {
    for (const status of ['answered', 'no_folder', 'no_file', 'no_passage', 'insufficient']) {
      expect(isRagStatus(status)).toBe(true)
    }
    expect(isRagStatus('weird')).toBe(false)
  })
})

describe('isRagOutput', () => {
  it('should accept a complete output', () => {
    expect(isRagOutput(answered)).toBe(true)
  })

  it('should accept a file step that spans several folder questions', () => {
    const fileStep = {
      ...answered.steps[1],
      selected: ['returns__refund_timeline', 'membership__points'],
      labels: {
        returns__refund_timeline: '환불 시점',
        none__returns: '해당 없음 (returns)',
        membership__points: '적립금',
        none__membership: '해당 없음 (membership)',
      },
      probabilities: {
        membership__points: 0.9,
        none__membership: 0.03,
        returns__refund_timeline: 0.8,
        none__returns: 0.05,
      },
    }

    expect(isRagOutput({ ...answered, steps: [answered.steps[0], fileStep] })).toBe(true)
  })

  it('should accept a stopped output with null answer and grounding', () => {
    expect(isRagOutput({ ...answered, status: 'no_file', answer: null, grounding: null })).toBe(true)
  })

  it('should accept the refusal-shaped output where sufficiency passed but the run stopped', () => {
    const sufficiencyStep = {
      kind: 'sufficiency',
      verdict: 'sufficient',
      selected: ['sufficient'],
      labels: {},
      probabilities: { sufficient: 0.82 },
      threshold: 0.5,
      latency_ms: 150,
      cost: 0.00001,
    }

    expect(
      isRagOutput({
        ...answered,
        status: 'insufficient',
        steps: [...answered.steps.slice(0, 2), sufficiencyStep],
        answer: null,
        grounding: null,
      }),
    ).toBe(true)
  })

  it('should accept an unknown status string', () => {
    expect(isRagOutput({ ...answered, status: 'weird' })).toBe(true)
  })

  it.each<[string, unknown]>([
    ['null', null],
    ['a string', 'answered'],
    ['an array', []],
    ['missing steps', { ...answered, steps: undefined }],
    ['non-array folders', { ...answered, folders: 'shipping' }],
    ['non-array passages', { ...answered, passages: {} }],
    ['numeric answer', { ...answered, answer: 7 }],
    ['numeric grounding', { ...answered, grounding: 1 }],
    ['non-string status', { ...answered, status: 1 }],
    ['selected that is not an array', withStep({ selected: 'shipping' })],
    ['selected holding a non-string', withStep({ selected: [1] })],
    ['null probabilities', withStep({ probabilities: null })],
    ['array probabilities', withStep({ probabilities: [0.5] })],
    ['probabilities holding a string', withStep({ probabilities: { shipping: 'high' } })],
    ['null labels', withStep({ labels: null })],
    ['array labels', withStep({ labels: [] })],
    ['labels holding an object', withStep({ labels: { shipping: { bad: true } } })],
    ['labels holding a number', withStep({ labels: { shipping: 7 } })],
    ['string threshold', withStep({ threshold: '0.25' })],
    ['string latency_ms', withStep({ latency_ms: '210' })],
    ['missing cost', withStep({ cost: undefined })],
    ['non-string kind', withStep({ kind: 1 })],
    ['non-string verdict', withStep({ verdict: null })],
    ['null step', { ...answered, steps: [null] }],
    ['passage without line', { ...answered, passages: [{ path: 'a.md', text: '본문' }] }],
    ['passage with numeric text', { ...answered, passages: [{ path: 'a.md', line: 1, text: 5 }] }],
    ['passage without path', { ...answered, passages: [{ line: 1, text: '본문' }] }],
  ])('should reject a malformed output: %s', (_name, value) => {
    expect(isRagOutput(value)).toBe(false)
  })
})
