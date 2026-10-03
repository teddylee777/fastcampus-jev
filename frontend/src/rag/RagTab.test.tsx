import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { runGraph } from '../lib/langgraph'
import { RagTab } from './RagTab'
import { isRagOutput, type RagOutput, type RagStep, type RagStepKind } from './types'

vi.mock('../lib/langgraph', () => ({ runGraph: vi.fn() }))

const runGraphMock = vi.mocked(runGraph)

const FIRST_QUERY = '배송비는 얼마인가요?'
const SECOND_QUERY = '환불하면 사용한 적립금은 어떻게 되나요?'
const FILE_KEY = 'shipping__delivery_fee'

const STEP_DEFAULTS: Record<RagStepKind, RagStep> = {
  folder: {
    kind: 'folder',
    verdict: 'shipping',
    selected: ['shipping'],
    labels: {},
    probabilities: { shipping: 0.91, returns: 0.12, none: 0.04 },
    threshold: 0.25,
    latency_ms: 10,
    cost: 0.00001,
  },
  file: {
    kind: 'file',
    verdict: FILE_KEY,
    selected: [FILE_KEY],
    labels: { [FILE_KEY]: '배송비 안내', none__shipping: '해당 없음 (shipping)' },
    probabilities: { [FILE_KEY]: 0.88, none__shipping: 0.02 },
    threshold: 0.2,
    latency_ms: 10,
    cost: 0.00001,
  },
  sufficiency: {
    kind: 'sufficiency',
    verdict: 'sufficient',
    selected: ['sufficient'],
    labels: {},
    probabilities: { sufficient: 0.82 },
    threshold: 0.5,
    latency_ms: 10,
    cost: 0.00001,
  },
  grounding: {
    kind: 'grounding',
    verdict: 'supports',
    selected: ['supports'],
    labels: {},
    probabilities: { supports: 0.9, contradicts: 0.02, says_nothing: 0.08 },
    threshold: null,
    latency_ms: 10,
    cost: 0.00001,
  },
}

function makeStep(kind: RagStepKind, patch: Partial<RagStep> = {}): RagStep {
  return { ...STEP_DEFAULTS[kind], ...patch }
}

function makeOutput(patch: Partial<RagOutput> = {}): RagOutput {
  return {
    status: 'answered',
    steps: [makeStep('folder'), makeStep('file'), makeStep('sufficiency'), makeStep('grounding')],
    folders: ['shipping'],
    files: ['shipping/delivery_fee.md'],
    passages: [{ path: 'shipping/delivery_fee.md', line: 3, text: '배송비는 3,000원입니다.' }],
    answer: '배송비는 3,000원입니다.',
    grounding: 'supports',
    ...patch,
  }
}

function renderTab() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <RagTab />
    </QueryClientProvider>,
  )
}

async function submitQuery(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: '문서에서 찾기' }))
}

function itemOf(heading: string): HTMLElement {
  const item = screen.getByRole('heading', { level: 3, name: heading }).closest('li')
  if (!item) throw new Error(`${heading} 항목을 찾지 못했습니다.`)
  return item
}

function badgeOf(heading: string): string {
  return itemOf(heading).querySelector('.verdict')?.textContent ?? ''
}

beforeEach(() => {
  runGraphMock.mockReset()
})

describe('RagTab', () => {
  it('should start with the first example and send the chosen example query to the doc_rag graph', async () => {
    runGraphMock.mockResolvedValue(makeOutput())
    const user = userEvent.setup()
    renderTab()

    const chips = screen.getAllByRole('button', { pressed: true })
    expect(screen.getByLabelText('질의')).toHaveValue(FIRST_QUERY)
    expect(chips).toHaveLength(1)
    expect(chips[0]).toHaveTextContent('정상')

    await user.click(screen.getByRole('button', { name: '두 폴더에 걸침' }))
    await submitQuery(user)

    expect(runGraphMock).toHaveBeenCalledTimes(1)
    expect(runGraphMock).toHaveBeenCalledWith('doc_rag', { query: SECOND_QUERY }, isRagOutput)

    await user.type(screen.getByLabelText('질의'), ' 알려 주세요')
    expect(screen.queryAllByRole('button', { pressed: true })).toHaveLength(0)
  })

  it('should keep an empty status region mounted before any run', () => {
    renderTab()

    expect(screen.getByRole('status')).toBeEmptyDOMElement()
    expect(screen.queryByRole('region', { name: 'RAG 결과' })).not.toBeInTheDocument()
  })

  it('should show sections in the policy order', async () => {
    runGraphMock.mockResolvedValue(makeOutput())
    const user = userEvent.setup()
    renderTab()

    await submitQuery(user)
    await screen.findByRole('region', { name: 'RAG 결과' })

    expect(screen.getByRole('heading', { level: 1, name: '문서 RAG' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: '결과' })).toBeInTheDocument()
    expect(screen.getAllByRole('heading', { level: 3 }).map((heading) => heading.textContent)).toEqual([
      '폴더 선택',
      '파일 선택',
      '찾은 구절',
      '충분성',
      '답변',
      '근거 검증',
    ])
    expect(screen.getByRole('meter', { name: 'shipping probability' })).toHaveAttribute('aria-valuenow', '91')
    expect(screen.getByRole('meter', { name: '배송비 안내 probability' })).toHaveAttribute('aria-valuenow', '88')
    expect(screen.getByText('shipping/delivery_fee.md:3')).toBeInTheDocument()
    expect(screen.getByText('배송비는 3,000원입니다.', { selector: '.rag-passage-text' })).toBeInTheDocument()
    expect(screen.getByText(`보낸 질의: ${FIRST_QUERY}`)).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('답변을 만들었습니다.')
    expect(screen.getAllByText(/^기준 /).map((note) => note.textContent)).toEqual([
      '기준 0.25',
      '기준 0.2',
      '기준 0.5',
    ])
  })

  it('should show every bar of a two-folder file step grouped by folder', async () => {
    // 서버 순서: 폴더 이름순, 폴더 안에서는 파일 뒤에 그 폴더의 "해당 없음". 값은 일부러 정렬 순서와 다르게 둔다.
    const fileKeys = [
      'returns__refund_timeline',
      'returns__return_window',
      'none__returns',
      'shipping__delivery_fee',
      'shipping__delivery_time',
      'shipping__international',
      'none__shipping',
    ]
    const fileStep = makeStep('file', {
      selected: ['returns__refund_timeline', 'shipping__delivery_fee'],
      labels: {
        returns__refund_timeline: '환불 시점',
        returns__return_window: '반품 기간',
        none__returns: '해당 없음 (returns)',
        shipping__delivery_fee: '배송비 안내',
        shipping__delivery_time: '배송 기간',
        shipping__international: '해외 배송',
        none__shipping: '해당 없음 (shipping)',
      },
      probabilities: Object.fromEntries(fileKeys.map((key, index) => [key, [0.1, 0.05, 0.02, 0.9, 0.3, 0.07, 0.01][index]])),
    })
    runGraphMock.mockResolvedValue(makeOutput({ steps: [makeStep('folder'), fileStep] }))
    const user = userEvent.setup()
    renderTab()

    await submitQuery(user)
    await screen.findByRole('region', { name: 'RAG 결과' })

    const meters = within(itemOf('파일 선택')).getAllByRole('meter')
    expect(meters.map((meter) => meter.getAttribute('aria-label'))).toEqual([
      '환불 시점 probability',
      '반품 기간 probability',
      '해당 없음 (returns) probability',
      '배송비 안내 probability',
      '배송 기간 probability',
      '해외 배송 probability',
      '해당 없음 (shipping) probability',
    ])
    expect(screen.queryByText('none__returns')).not.toBeInTheDocument()
    expect(screen.queryByText('none__shipping')).not.toBeInTheDocument()
  })

  it('should explain that file probabilities are asked per folder', async () => {
    runGraphMock.mockResolvedValue(makeOutput())
    const user = userEvent.setup()
    renderTab()

    await submitQuery(user)
    await screen.findByRole('region', { name: 'RAG 결과' })

    const note = '폴더마다 따로 물은 probability 입니다.'
    expect(within(itemOf('파일 선택')).getByText(new RegExp(note))).toBeInTheDocument()
    expect(within(itemOf('폴더 선택')).queryByText(new RegExp(note))).not.toBeInTheDocument()
    expect(screen.getAllByText(new RegExp(note))).toHaveLength(1)
  })

  it('should show verdict badges with Korean labels', async () => {
    runGraphMock.mockResolvedValue(makeOutput())
    const user = userEvent.setup()
    renderTab()

    await submitQuery(user)
    await screen.findByRole('region', { name: 'RAG 결과' })

    expect(badgeOf('폴더 선택')).toBe('shipping')
    expect(badgeOf('파일 선택')).toBe('배송비 안내')
    expect(badgeOf('충분성')).toBe('충분함')
    expect(badgeOf('근거 검증')).toBe('근거 있음')
    expect(screen.queryByText(FILE_KEY)).not.toBeInTheDocument()
    expect(screen.queryByText('supports')).not.toBeInTheDocument()
    expect(within(itemOf('근거 검증')).getAllByText('근거 있음')).toHaveLength(2)
  })

  it('should show the Jev call count, total latency and total cost', async () => {
    runGraphMock.mockResolvedValue(makeOutput())
    const user = userEvent.setup()
    renderTab()

    await submitQuery(user)

    expect(await screen.findByText('4회 · 40ms · $0.000040')).toBeInTheDocument()
  })

  it.each<[string, string, RagOutput, string[]]>([
    [
      'no_folder',
      '문서에 없는 내용입니다. 폴더 선택에서 맞는 폴더가 없었습니다.',
      makeOutput({
        status: 'no_folder',
        steps: [
          makeStep('folder', {
            verdict: 'none',
            selected: [],
            probabilities: { none: 0.9, shipping: 0.1 },
          }),
        ],
        folders: [],
        files: [],
        passages: [],
        answer: null,
        grounding: null,
      }),
      ['폴더 선택'],
    ],
    [
      'no_file',
      '문서에 없는 내용입니다. 파일 선택에서 맞는 파일이 없었습니다.',
      makeOutput({
        status: 'no_file',
        steps: [makeStep('folder'), makeStep('file', { verdict: 'none', selected: [] })],
        files: [],
        passages: [],
        answer: null,
        grounding: null,
      }),
      ['폴더 선택', '파일 선택'],
    ],
    [
      'no_passage',
      '문서에서 찾지 못했습니다. 고른 파일에 질의 낱말이 든 구절이 없습니다.',
      makeOutput({
        status: 'no_passage',
        steps: [makeStep('folder'), makeStep('file')],
        passages: [],
        answer: null,
        grounding: null,
      }),
      ['폴더 선택', '파일 선택'],
    ],
    [
      'insufficient',
      '문서에서 찾지 못했습니다. 찾은 구절만으로는 답할 수 없다고 판단했습니다.',
      makeOutput({
        status: 'insufficient',
        steps: [
          makeStep('folder'),
          makeStep('file'),
          makeStep('sufficiency', { verdict: 'insufficient', selected: [], probabilities: { sufficient: 0.2 } }),
        ],
        answer: null,
        grounding: null,
      }),
      ['폴더 선택', '파일 선택', '찾은 구절', '충분성'],
    ],
  ])('should show the stop reason for the %s status', async (_status, reason, output, headings) => {
    runGraphMock.mockResolvedValue(output)
    const user = userEvent.setup()
    renderTab()

    await submitQuery(user)
    await screen.findByRole('region', { name: 'RAG 결과' })

    expect(screen.getByRole('status')).toHaveTextContent(reason)
    expect(screen.queryByRole('heading', { level: 3, name: '답변' })).not.toBeInTheDocument()
    expect(screen.getAllByRole('heading', { level: 3 }).map((heading) => heading.textContent)).toEqual(headings)
  })

  it('should say the LLM declined when Jev judged the passages sufficient but the run still ended insufficient', async () => {
    runGraphMock.mockResolvedValue(
      makeOutput({
        status: 'insufficient',
        steps: [makeStep('folder'), makeStep('file'), makeStep('sufficiency')],
        answer: null,
        grounding: null,
      }),
    )
    const user = userEvent.setup()
    renderTab()

    await submitQuery(user)
    await screen.findByRole('region', { name: 'RAG 결과' })

    expect(screen.getByRole('status')).toHaveTextContent(
      'Jev 는 찾은 구절이 충분하다고 판단했지만, LLM 이 그 구절로는 답하지 못한다고 답했습니다.',
    )
    expect(screen.getByRole('status')).not.toHaveTextContent('찾은 구절만으로는 답할 수 없다고 판단했습니다.')
    expect(badgeOf('충분성')).toBe('충분함')
  })

  it('should show the per-folder not-applicable bar when no file matched', async () => {
    runGraphMock.mockResolvedValue(
      makeOutput({
        status: 'no_file',
        steps: [makeStep('folder'), makeStep('file', { verdict: 'none', selected: [] })],
        files: [],
        passages: [],
        answer: null,
        grounding: null,
      }),
    )
    const user = userEvent.setup()
    renderTab()

    await submitQuery(user)
    await screen.findByRole('region', { name: 'RAG 결과' })

    expect(within(itemOf('파일 선택')).getByRole('meter', { name: '해당 없음 (shipping) probability' })).toHaveAttribute(
      'aria-valuenow',
      '2',
    )
    expect(badgeOf('파일 선택')).toBe('해당 없음')
  })

  it('should show a none bar and the not-applicable badge when no folder matched', async () => {
    runGraphMock.mockResolvedValue(
      makeOutput({
        status: 'no_folder',
        steps: [makeStep('folder', { verdict: 'none', selected: [], probabilities: { none: 0.9, shipping: 0.1 } })],
        passages: [],
        answer: null,
        grounding: null,
      }),
    )
    const user = userEvent.setup()
    renderTab()

    await submitQuery(user)
    await screen.findByRole('region', { name: 'RAG 결과' })

    expect(screen.getByRole('meter', { name: '해당 없음 probability' })).toHaveAttribute('aria-valuenow', '90')
    expect(badgeOf('폴더 선택')).toBe('해당 없음')
  })

  it('should show an insufficient badge when the sufficiency step did not pass', async () => {
    runGraphMock.mockResolvedValue(
      makeOutput({
        status: 'insufficient',
        steps: [makeStep('sufficiency', { verdict: 'insufficient', selected: [], probabilities: { sufficient: 0.2 } })],
        answer: null,
        grounding: null,
      }),
    )
    const user = userEvent.setup()
    renderTab()

    await submitQuery(user)
    await screen.findByRole('region', { name: 'RAG 결과' })

    expect(badgeOf('충분성')).toBe('부족함')
  })

  it('should mark the answer only when grounding is not supports', async () => {
    const user = userEvent.setup()
    runGraphMock.mockResolvedValueOnce(
      makeOutput({
        grounding: 'contradicts',
        steps: [makeStep('grounding', { verdict: 'contradicts', selected: ['contradicts'] })],
      }),
    )
    renderTab()

    await submitQuery(user)
    await screen.findByRole('heading', { level: 3, name: '답변' })

    expect(within(itemOf('답변')).getByText('근거 확인 필요')).toBeInTheDocument()
    expect(within(itemOf('답변')).getByText('배송비는 3,000원입니다.')).toBeInTheDocument()
    expect(badgeOf('근거 검증')).toBe('어긋남')

    runGraphMock.mockResolvedValueOnce(makeOutput())
    await submitQuery(user)
    await screen.findByText('근거 있음', { selector: '.verdict' })

    expect(screen.queryByText('근거 확인 필요')).not.toBeInTheDocument()
  })

  it('should show the pending state while the request is running', async () => {
    runGraphMock.mockReturnValue(new Promise<RagOutput>(() => {}))
    const user = userEvent.setup()
    renderTab()

    await submitQuery(user)

    expect(await screen.findByRole('button', { name: '찾는 중…' })).toBeDisabled()
    expect(screen.getByRole('status')).toHaveTextContent('문서에서 찾는 중입니다.')
  })

  it('should disable submit when the query is blank', async () => {
    const user = userEvent.setup()
    renderTab()
    const queryBox = screen.getByLabelText('질의')

    await user.clear(queryBox)
    expect(screen.getByRole('button', { name: '문서에서 찾기' })).toBeDisabled()

    await user.type(queryBox, '   ')
    expect(screen.getByRole('button', { name: '문서에서 찾기' })).toBeDisabled()

    await user.click(screen.getByRole('button', { name: '문서에서 찾기' }))
    expect(runGraphMock).not.toHaveBeenCalled()
  })

  it('should clear the result when an example chip is clicked', async () => {
    runGraphMock.mockResolvedValue(makeOutput())
    const user = userEvent.setup()
    renderTab()

    await submitQuery(user)
    await screen.findByRole('region', { name: 'RAG 결과' })
    expect(screen.getByRole('status')).not.toBeEmptyDOMElement()

    await user.click(screen.getByRole('button', { name: '문서에 없음' }))

    expect(screen.queryByRole('region', { name: 'RAG 결과' })).not.toBeInTheDocument()
    expect(screen.getByRole('status')).toBeEmptyDOMElement()
    expect(screen.getByLabelText('질의')).toHaveValue('주차장 약도를 팩스로 보내주세요')
  })

  it('should render markup-like text literally', async () => {
    runGraphMock.mockResolvedValue(
      makeOutput({
        answer: '**굵게** <b>x</b>',
        passages: [{ path: 'a/b.md', line: 1, text: '<i>본문</i> **강조**' }],
      }),
    )
    const user = userEvent.setup()
    const { container } = renderTab()

    await submitQuery(user)

    expect(await screen.findByText('**굵게** <b>x</b>')).toBeInTheDocument()
    expect(screen.getByText('<i>본문</i> **강조**')).toBeInTheDocument()
    expect(container.querySelector('.rag-answer > *, .rag-passage-text > *')).toBeNull()
  })

  it('should show a fallback line for an unknown status', async () => {
    runGraphMock.mockResolvedValue(makeOutput({ status: 'weird', steps: [], passages: [], answer: null }))
    const user = userEvent.setup()
    renderTab()

    await submitQuery(user)

    expect(await screen.findByText('알 수 없는 상태입니다: weird')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { level: 3 })).not.toBeInTheDocument()
  })

  it('should show the server error as an alert', async () => {
    runGraphMock.mockRejectedValue(new Error('402 Payment Required'))
    const user = userEvent.setup()
    renderTab()

    await submitQuery(user)

    expect(await screen.findByRole('alert')).toHaveTextContent('실행하지 못했습니다: 402 Payment Required')
    expect(screen.queryByRole('region', { name: 'RAG 결과' })).not.toBeInTheDocument()
    expect(screen.getByRole('status')).toBeEmptyDOMElement()
  })
})
