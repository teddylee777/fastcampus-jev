import { useRef, useState, type KeyboardEvent } from 'react'
import { ChatTab } from './chat/ChatTab'
import { PatternTab } from './patterns/PatternTab'
import { PATTERNS } from './patterns/config'
import { RagTab } from './rag/RagTab'
import './App.css'

const CHAT_TAB = 'chat'
const RAG_TAB = 'doc-rag'
const REPO_URL = 'https://github.com/teddylee777/fastcampus-jev'
const TABS = [
  { id: CHAT_TAB, title: '고객지원 에이전트', group: '샘플 프로젝트' },
  ...PATTERNS.map((pattern) => ({ id: pattern.id, title: pattern.title, group: pattern.group })),
  { id: RAG_TAB, title: '문서 RAG', group: 'RAG' },
]
const KEY_STEP: Record<string, number> = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 }

export default function App() {
  const [activeTab, setActiveTab] = useState(CHAT_TAB)
  const [chatSession, setChatSession] = useState(0)
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({})

  const moveFocus = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const step = KEY_STEP[event.key]
    if (!step) return
    event.preventDefault()
    const next = TABS[(index + step + TABS.length) % TABS.length]
    setActiveTab(next.id)
    tabRefs.current[next.id]?.focus()
  }
  const startNewChat = () => {
    setChatSession((session) => session + 1) // key 가 바뀌면 새 스레드로 다시 시작한다.
    setActiveTab(CHAT_TAB)
  }

  return (
    <div className="app">
      <nav className="sidebar" aria-label="화면 선택">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            J
          </span>
          <div>
            <strong>Jev Lab</strong>
            <span>비법노트 주주총회</span>
          </div>
        </div>
        <button type="button" className="new-chat" onClick={startNewChat}>
          + 새 대화
        </button>
        <div className="tabs" role="tablist" aria-orientation="vertical">
          {TABS.map((tab, index) => (
            <div key={tab.id} className="tab-slot">
              {(index === 0 || TABS[index - 1].group !== tab.group) && (
                <p className="tab-group">{tab.group}</p>
              )}
              <button
                ref={(element) => {
                  tabRefs.current[tab.id] = element
                }}
                type="button"
                role="tab"
                id={`tab-${tab.id}`}
                aria-selected={activeTab === tab.id}
                aria-controls={`panel-${tab.id}`}
                tabIndex={activeTab === tab.id ? 0 : -1}
                className="tab"
                onClick={() => setActiveTab(tab.id)}
                onKeyDown={(event) => moveFocus(event, index)}
              >
                {tab.title}
              </button>
            </div>
          ))}
        </div>
        <a
          className="repo-link"
          href={REPO_URL}
          target="_blank"
          rel="noopener noreferrer"
          aria-label="GitHub 저장소 (새 창)"
        >
          GitHub
        </a>
        <p className="sidebar-foot">판단은 Jev 에게, 말은 LLM 에게</p>
      </nav>

      <main className="stage">
        {/* 채팅은 탭을 옮겨도 대화가 유지되도록 숨기기만 한다. */}
        <div
          role="tabpanel"
          id={`panel-${CHAT_TAB}`}
          aria-labelledby={`tab-${CHAT_TAB}`}
          className="tabpanel"
          hidden={activeTab !== CHAT_TAB}
        >
          <ChatTab key={chatSession} />
        </div>
        {PATTERNS.filter((pattern) => pattern.id === activeTab).map((pattern) => (
          <div
            key={pattern.id}
            role="tabpanel"
            id={`panel-${pattern.id}`}
            aria-labelledby={`tab-${pattern.id}`}
            className="tabpanel"
          >
            <PatternTab config={pattern} />
          </div>
        ))}
        {activeTab === RAG_TAB && (
          <div
            role="tabpanel"
            id={`panel-${RAG_TAB}`}
            aria-labelledby={`tab-${RAG_TAB}`}
            className="tabpanel"
          >
            <RagTab />
          </div>
        )}
      </main>
    </div>
  )
}
