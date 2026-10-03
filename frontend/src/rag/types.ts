export const RAG_STATUSES = ['answered', 'no_folder', 'no_file', 'no_passage', 'insufficient'] as const
export type RagStatus = (typeof RAG_STATUSES)[number]
export type RagStepKind = 'folder' | 'file' | 'sufficiency' | 'grounding'

export type RagStep = {
  kind: RagStepKind
  verdict: string
  selected: string[]
  labels: Record<string, string>
  probabilities: Record<string, number>
  threshold: number | null
  latency_ms: number
  cost: number
}
export type RagPassage = { path: string; line: number; text: string }

/** `status` 와 `grounding` 은 서버가 모르는 값을 보내도 화면이 깨지지 않도록 string 으로 둔다. */
export type RagOutput = {
  status: string
  steps: RagStep[]
  folders: string[]
  files: string[]
  passages: RagPassage[]
  answer: string | null
  grounding: string | null
}

export function isRagStatus(status: string): status is RagStatus {
  return (RAG_STATUSES as readonly string[]).includes(status)
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string')
}

function isNumber(value: unknown): value is number {
  return typeof value === 'number'
}

function isStringOrNull(value: unknown): value is string | null {
  return value === null || typeof value === 'string'
}

function isRecordOf(value: unknown, isValue: (item: unknown) => boolean): boolean {
  return isRecord(value) && Object.values(value).every(isValue)
}

function isRagStep(value: unknown): value is RagStep {
  return (
    isRecord(value) &&
    typeof value.kind === 'string' &&
    typeof value.verdict === 'string' &&
    isStringArray(value.selected) &&
    // `ProbabilityBars` 가 labels 값을 React 자식으로 그리므로 문자열이 아니면 렌더 중에 터진다.
    isRecordOf(value.labels, (label) => typeof label === 'string') &&
    isRecordOf(value.probabilities, isNumber) &&
    (value.threshold === null || isNumber(value.threshold)) &&
    isNumber(value.latency_ms) &&
    isNumber(value.cost)
  )
}

function isRagPassage(value: unknown): value is RagPassage {
  return (
    isRecord(value) &&
    typeof value.path === 'string' &&
    isNumber(value.line) &&
    typeof value.text === 'string'
  )
}

/**
 * 서버 응답이 화면이 역참조하는 모양인지 확인한다. `status` 와 `kind` 의 값 자체는 보지 않는다.
 * error boundary 가 없어서, 모양이 틀린 응답이 렌더까지 가면 앱 전체가 빈 화면이 된다.
 */
export function isRagOutput(value: unknown): value is RagOutput {
  return (
    isRecord(value) &&
    typeof value.status === 'string' &&
    Array.isArray(value.steps) &&
    value.steps.every(isRagStep) &&
    isStringArray(value.folders) &&
    isStringArray(value.files) &&
    Array.isArray(value.passages) &&
    value.passages.every(isRagPassage) &&
    isStringOrNull(value.answer) &&
    isStringOrNull(value.grounding)
  )
}
