import { useState, type FormEvent } from 'react'
import { useMutation } from '@tanstack/react-query'
import { ProbabilityBars } from '../components/ProbabilityBars'
import { runGraph } from '../lib/langgraph'
import { isRagOutput, isRagStatus, type RagOutput, type RagStatus, type RagStep, type RagStepKind } from './types'

type Tone = 'good' | 'warn' | 'bad' | 'neutral'

// 서버 SAMPLE_QUERIES 의 문장을 그대로 옮긴 것이다. 서버 목록이 기준이다.
const EXAMPLES = [
  { label: '정상', query: '배송비는 얼마인가요?' },
  { label: '두 폴더에 걸침', query: '환불하면 사용한 적립금은 어떻게 되나요?' },
  { label: '문서에 없음', query: '주차장 약도를 팩스로 보내주세요' },
]

const STOP_REASONS: Record<Exclude<RagStatus, 'answered'>, string> = {
  no_folder: '문서에 없는 내용입니다. 폴더 선택에서 맞는 폴더가 없었습니다.',
  no_file: '문서에 없는 내용입니다. 파일 선택에서 맞는 파일이 없었습니다.',
  no_passage: '문서에서 찾지 못했습니다. 고른 파일에 질의 낱말이 든 구절이 없습니다.',
  insufficient: '문서에서 찾지 못했습니다. 찾은 구절만으로는 답할 수 없다고 판단했습니다.',
}

const STEP_LABELS: Record<string, string> = {
  none: '해당 없음',
  sufficient: '충분함',
  supports: '근거 있음',
  contradicts: '어긋남',
  says_nothing: '언급 없음',
}

const TONE_CLASSES: Record<Tone, string> = {
  good: 'tone-good',
  warn: 'tone-warn',
  bad: 'tone-bad',
  neutral: 'tone-neutral',
}

const GROUNDING_TONES: Record<string, Tone> = {
  supports: 'good',
  says_nothing: 'warn',
  contradicts: 'bad',
}

const STEP_TITLES: Record<RagStepKind, string> = {
  folder: '폴더 선택',
  file: '파일 선택',
  sufficiency: '충분성',
  grounding: '근거 검증',
}

function describeStatus(status: string): string {
  if (!isRagStatus(status)) return `알 수 없는 상태입니다: ${status}`
  return status === 'answered' ? '답변을 만들었습니다.' : STOP_REASONS[status]
}

function toneOf(step: RagStep): Tone {
  const hasSelection = step.selected.length > 0
  if (step.kind === 'folder' || step.kind === 'file') return hasSelection ? 'good' : 'neutral'
  if (step.kind === 'sufficiency') return hasSelection ? 'good' : 'warn'
  return GROUNDING_TONES[step.selected[0]] ?? 'neutral'
}

function badgeOf(step: RagStep, labels: Record<string, string>): string {
  if (step.selected.length > 0) return step.selected.map((key) => labels[key] ?? key).join(', ')
  return step.kind === 'sufficiency' ? '부족함' : STEP_LABELS.none
}

/** Jev 판단 한 번의 결과: 제목, 한국어 배지, 기준값, probability 막대. */
function StepResult({ step }: { step: RagStep }) {
  const labels = { ...STEP_LABELS, ...step.labels }
  const tone = TONE_CLASSES[toneOf(step)]
  return (
    <li className={`result-row ${tone}`}>
      <div className="result-head">
        <h3>{STEP_TITLES[step.kind]}</h3>
        <span className={`verdict ${tone}`}>{badgeOf(step, labels)}</span>
      </div>
      {step.threshold !== null && <p className="result-note">{`기준 ${step.threshold}`}</p>}
      {step.kind === 'file' && (
        <p className="result-note">폴더마다 따로 물은 probability 입니다. 폴더가 여럿이면 합이 1 을 넘습니다.</p>
      )}
      <ProbabilityBars
        probabilities={step.probabilities}
        highlighted={step.selected}
        labels={labels}
        maxBars={Object.keys(step.probabilities).length}
        keepOrder={step.kind === 'file'}
      />
    </li>
  )
}

function ResultSection({ output, query }: { output: RagOutput; query: string }) {
  const stepOf = (kind: RagStepKind) => output.steps.find((step) => step.kind === kind)
  const folder = stepOf('folder')
  const file = stepOf('file')
  const sufficiency = stepOf('sufficiency')
  const grounding = stepOf('grounding')
  const totalLatencyMs = output.steps.reduce((total, step) => total + step.latency_ms, 0)
  const totalCost = output.steps.reduce((total, step) => total + step.cost, 0)
  const needsGroundingCheck = output.status === 'answered' && output.grounding !== 'supports'

  return (
    <section className="result" aria-label="RAG 결과">
      <h2>결과</h2>
      <p className="result-note">{`보낸 질의: ${query}`}</p>
      <ul className="stats">
        <li>
          <span>Jev 호출</span>
          <strong>{`${output.steps.length}회 · ${totalLatencyMs}ms · $${totalCost.toFixed(6)}`}</strong>
        </li>
      </ul>
      <ol className="result-rows">
        {folder && <StepResult step={folder} />}
        {file && <StepResult step={file} />}
        {output.passages.length > 0 && (
          <li className="result-row tone-neutral">
            <div className="result-head">
              <h3>찾은 구절</h3>
            </div>
            <ul className="rag-passages">
              {output.passages.map((passage, index) => (
                <li key={`${passage.path}:${passage.line}:${index}`}>
                  <p className="rag-passage-source">{`${passage.path}:${passage.line}`}</p>
                  <p className="rag-passage-text">{passage.text}</p>
                </li>
              ))}
            </ul>
          </li>
        )}
        {sufficiency && <StepResult step={sufficiency} />}
        {output.answer !== null && (
          <li className="result-row tone-neutral">
            <div className="result-head">
              <h3>답변</h3>
              {needsGroundingCheck && <span className="verdict tone-warn">근거 확인 필요</span>}
            </div>
            <p className="rag-answer">{output.answer}</p>
          </li>
        )}
        {grounding && <StepResult step={grounding} />}
      </ol>
    </section>
  )
}

/** 문서 RAG 그래프를 직접 실행해 보는 탭. 폴더 선택부터 근거 검증까지 단계 순서대로 보여 준다. */
export function RagTab() {
  const [query, setQuery] = useState(EXAMPLES[0].query)

  const mutation = useMutation({
    mutationFn: (question: string) => runGraph('doc_rag', { query: question }, isRagOutput),
  })

  const chooseExample = (example: string) => {
    setQuery(example)
    mutation.reset()
  }
  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    mutation.mutate(query)
  }

  let statusMessage: string | null = null
  if (mutation.isPending) statusMessage = '문서에서 찾는 중입니다.'
  else if (mutation.isSuccess) statusMessage = describeStatus(mutation.data.status)

  return (
    <div className="pattern">
      <header className="topbar">
        <div>
          <h1>문서 RAG</h1>
          <p>Jev 가 어느 폴더와 파일을 볼지, 답해도 되는지를 판단하고 LLM 이 답을 씁니다.</p>
        </div>
      </header>

      <div className="pattern-body">
        <form className="pattern-form" onSubmit={onSubmit}>
          <div className="chips" role="group" aria-label="예시 선택">
            {EXAMPLES.map((example) => (
              <button
                key={example.label}
                type="button"
                className="chip"
                aria-pressed={query === example.query}
                onClick={() => chooseExample(example.query)}
              >
                {example.label}
              </button>
            ))}
          </div>

          <div className="field">
            <label htmlFor="rag-query">질의</label>
            <textarea
              id="rag-query"
              rows={2}
              maxLength={4000}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>

          <button type="submit" className="primary" disabled={mutation.isPending || query.trim() === ''}>
            {mutation.isPending ? '찾는 중…' : '문서에서 찾기'}
          </button>
        </form>

        <p className="rag-status" role="status">
          {statusMessage}
        </p>

        {mutation.isError && (
          <p className="error" role="alert">
            실행하지 못했습니다: {mutation.error.message}
          </p>
        )}

        {mutation.isSuccess && <ResultSection output={mutation.data} query={mutation.variables} />}
      </div>
    </div>
  )
}
