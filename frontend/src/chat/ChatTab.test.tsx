import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ChatTab } from './ChatTab'

const streamState = vi.hoisted(() => ({ value: {} as Record<string, unknown> }))

vi.mock('@langchain/langgraph-sdk/react', () => ({ useStream: () => streamState.value }))

const idleStream = () => ({
  messages: [],
  values: {},
  interrupt: undefined,
  isLoading: false,
  error: undefined,
  submit: vi.fn(),
  stop: vi.fn(),
})

const GUARDRAIL_OFF_HINT = '가드레일 꺼짐: 검사 생략'

beforeEach(() => {
  streamState.value = idleStream()
})

describe('ChatTab', () => {
  it('should show the original guardrail hints while the switch is on', () => {
    render(<ChatTab />)

    expect(screen.getByText('가드레일: 차단')).toBeInTheDocument()
    expect(screen.queryByText(GUARDRAIL_OFF_HINT)).not.toBeInTheDocument()
  })

  it('should replace the four guardrail hints when the switch is turned off', async () => {
    const user = userEvent.setup()
    render(<ChatTab />)

    await user.click(screen.getByRole('button', { name: '가드레일 켜짐' }))

    expect(screen.getAllByText(GUARDRAIL_OFF_HINT)).toHaveLength(4)
    expect(screen.queryByText('가드레일: 차단')).not.toBeInTheDocument()
    expect(screen.getByText('도구 선택')).toBeInTheDocument()
    expect(screen.getByText('위험 게이트 자동 승인')).toBeInTheDocument()
    expect(screen.getByText('사람 확인 요청')).toBeInTheDocument()
  })

  it('should restore the original hints when the switch is turned back on', async () => {
    const user = userEvent.setup()
    render(<ChatTab />)

    await user.click(screen.getByRole('button', { name: '가드레일 켜짐' }))
    await user.click(screen.getByRole('button', { name: '가드레일 꺼짐' }))

    expect(screen.getByText('가드레일: 차단')).toBeInTheDocument()
    expect(screen.queryByText(GUARDRAIL_OFF_HINT)).not.toBeInTheDocument()
  })

  it('should pass the switch value to the stage label', async () => {
    const user = userEvent.setup()
    const { rerender } = render(<ChatTab />)

    await user.click(screen.getByRole('button', { name: '가드레일 켜짐' }))
    streamState.value = {
      ...idleStream(),
      isLoading: true,
      messages: [{ type: 'human', id: 'h1', content: 'A1002 불량이라 환불해 주세요' }],
    }
    rerender(<ChatTab />)

    expect(screen.getByText('요청을 처리하는 중')).toBeInTheDocument()
  })
})
