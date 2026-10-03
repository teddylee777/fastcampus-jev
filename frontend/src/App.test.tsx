import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import App from './App'

const submit = vi.hoisted(() => vi.fn())

vi.mock('@langchain/langgraph-sdk/react', () => ({
  useStream: () => ({
    messages: [
      { type: 'human', id: 'h1', content: 'A1001 어디쯤이에요?' },
      {
        type: 'ai',
        id: 'a1',
        content: '',
        tool_calls: [{ id: 'c1', name: 'track_shipping', args: { order_id: 'A1001' } }],
      },
      { type: 'tool', id: 't1', name: 'track_shipping', tool_call_id: 'c1', content: '옥천 허브 통과' },
      { type: 'ai', id: 'a2', content: '주문은 **내일 도착** 예정입니다.' },
    ],
    values: {
      jev_decisions: [
        {
          kind: 'tool_select',
          title: '도구 선택',
          verdict: 'track_shipping',
          latency_ms: 250,
          turn: 1,
          probabilities: { track_shipping: 0.99, search_order: 0.01 },
          offered: ['track_shipping'],
          confidence: 0.99,
        },
      ],
    },
    interrupt: undefined,
    isLoading: false,
    error: undefined,
    submit,
    stop: vi.fn(),
  }),
}))

function renderApp() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <App />
    </QueryClientProvider>,
  )
}

describe('App', () => {
  it('should render markdown in assistant answers instead of raw asterisks', () => {
    renderApp()

    expect(screen.getByText('내일 도착').tagName).toBe('STRONG')
    expect(screen.queryByText(/\*\*내일 도착\*\*/)).not.toBeInTheDocument()
  })

  it('should show the tool call with its arguments and result', () => {
    renderApp()

    expect(screen.getByText('order_id: A1001')).toBeInTheDocument()
    expect(screen.getByText('옥천 허브 통과')).toBeInTheDocument()
    expect(screen.getByText('완료')).toBeInTheDocument()
  })

  it('should show Jev decisions grouped by turn with a probability meter', () => {
    renderApp()

    expect(screen.getByRole('heading', { name: '턴 1' })).toBeInTheDocument()
    expect(screen.getByRole('meter', { name: 'track_shipping probability' })).toHaveAttribute(
      'aria-valuenow',
      '99',
    )
  })

  it('should send the guardrail switch with every run and default to on', async () => {
    const user = userEvent.setup()
    renderApp()

    const toggle = screen.getByRole('button', { name: '가드레일 켜짐' })
    expect(toggle).toHaveAttribute('aria-pressed', 'true')
    await user.type(screen.getByLabelText('메시지'), '쿠폰 사용 기간{Enter}')
    expect(submit.mock.lastCall?.[1].config).toEqual({ configurable: { guardrail_enabled: true } })

    await user.click(toggle)
    expect(screen.getByRole('button', { name: '가드레일 꺼짐' })).toHaveAttribute('aria-pressed', 'false')
    await user.type(screen.getByLabelText('메시지'), '쿠폰 사용 방법{Enter}')
    expect(submit.mock.lastCall?.[1].config).toEqual({ configurable: { guardrail_enabled: false } })
  })

  it('should switch to a pattern tab on click and keep the chat mounted but hidden', async () => {
    const user = userEvent.setup()
    renderApp()

    await user.click(screen.getByRole('tab', { name: '메모리 압축' }))

    expect(screen.getByRole('tab', { name: '메모리 압축' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('heading', { level: 1, name: '메모리 압축' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Jev 에 묻기' })).toBeInTheDocument()
    expect(document.getElementById('panel-chat')).toHaveAttribute('hidden')
  })

  it('should link to the GitHub repository from the sidebar', () => {
    renderApp()

    const link = screen.getByRole('link', { name: /GitHub/ })
    expect(link).toHaveAttribute('href', 'https://github.com/teddylee777/fastcampus-jev')
    expect(link).toHaveAttribute('target', '_blank')
  })

  it('should move between tabs with the arrow keys', async () => {
    const user = userEvent.setup()
    renderApp()

    screen.getByRole('tab', { name: '고객지원 에이전트' }).focus()
    await user.keyboard('{ArrowDown}')

    expect(screen.getByRole('tab', { name: '가드레일 비교' })).toHaveFocus()
    expect(screen.getByRole('tab', { name: '가드레일 비교' })).toHaveAttribute('aria-selected', 'true')

    await user.keyboard('{ArrowUp}{ArrowUp}')

    expect(screen.getByRole('tab', { name: '문서 RAG' })).toHaveFocus()
  })

  it('should switch to the document RAG tab on click', async () => {
    const user = userEvent.setup()
    renderApp()

    await user.click(screen.getByRole('tab', { name: '문서 RAG' }))

    expect(screen.getByRole('tab', { name: '문서 RAG' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('heading', { level: 1, name: '문서 RAG' })).toBeVisible()
    expect(screen.getByRole('button', { name: '문서에서 찾기' })).toBeInTheDocument()
    expect(document.getElementById('panel-doc-rag')).toHaveAttribute('aria-labelledby', 'tab-doc-rag')
    expect(document.getElementById('panel-chat')).toHaveAttribute('hidden')
  })
})
