import { useEffect, useMemo, useRef, useState } from 'react'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
const TOTAL_QUESTIONS = 10

const DEMO_CANDIDATE = {
  member: {
    id: 'CAND-001',
    name: 'Sarah Johnson',
    jobRole: 'Senior Data Engineer',
    yearsExperience: 9,
    education: 'MS Computer Science',
    status: 'COMPLETED',
  },
  missions: [
    { day: 7, title: 'Embeddings Explained', passed: true, attempts: 1 },
    { day: 8, title: 'Vector Databases Overview', passed: true, attempts: 1 },
    { day: 10, title: 'Retrieval & Matching Engine', passed: true, attempts: 2 },
    { day: 12, title: 'Prompt Engineering Fundamentals', passed: true, attempts: 4 },
    { day: 16, title: 'Chatbot Backend & API Integration', passed: true, attempts: 1 },
    { day: 22, title: 'Multi-Agent Orchestration', passed: true, attempts: 2 },
    { day: 23, title: 'Model Context Protocol (MCP)', passed: true, attempts: 2 },
    { day: 28, title: 'Docker & Kubernetes Deployment', passed: true, attempts: 3 },
    { day: 29, title: 'Monitoring, Logging & Observability', skipped: true },
    { day: 31, title: 'Capstone Project & Final Demo', passed: true, attempts: 1 },
  ],
  signals: {
    commitDays: 28,
    missionsCompleted: 30,
    missionsFirstTry: 20,
  },
}

function createSessionId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `interviewos-${crypto.randomUUID()}`
  }

  return `interviewos-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function getString(value, fallback) {
  return typeof value === 'string' && value.trim() ? value.trim() : fallback
}

function normalizeFeedback(feedback) {
  const safeFeedback = feedback && typeof feedback === 'object' ? feedback : {}

  return {
    summary: getString(safeFeedback.summary, 'No summary was returned by the backend.'),
    strengths: Array.isArray(safeFeedback.strengths) ? safeFeedback.strengths.filter(Boolean) : [],
    gaps: Array.isArray(safeFeedback.gaps) ? safeFeedback.gaps.filter(Boolean) : [],
    next: Array.isArray(safeFeedback.next) ? safeFeedback.next.filter(Boolean) : [],
  }
}

function normalizeErrorMessage(error, response) {
  if (error instanceof TypeError) {
    return 'InterviewOS backend is offline. Start the FastAPI server and try again.'
  }

  if (!response) {
    return error?.message || 'Something went wrong while talking to InterviewOS.'
  }

  switch (response.status) {
    case 404:
      return 'Interview endpoint not found. Start the FastAPI server and verify the API is available.'
    case 409:
      return 'A duplicate interview session was detected. Start a new interview to generate a fresh session.'
    case 410:
      return 'This interview session is no longer available. Start a new interview to continue.'
    case 500:
      return 'The InterviewOS backend returned an internal error. Try again in a moment.'
    default:
      return error?.message || 'InterviewOS returned an unexpected response.'
  }
}

async function readResponseBody(response) {
  const text = await response.text()

  if (!text) {
    return null
  }

  try {
    return JSON.parse(text)
  } catch {
    return { detail: text }
  }
}

async function postInterview(payload) {
  return fetch(`${API_BASE}/api/interview`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  })
}

function App() {
  const [view, setView] = useState('landing')
  const [candidate] = useState(DEMO_CANDIDATE)
  const [sessionId, setSessionId] = useState('')
  const [messages, setMessages] = useState([])
  const [currentQuestion, setCurrentQuestion] = useState('')
  const [questionNumber, setQuestionNumber] = useState(0)
  const [draft, setDraft] = useState('')
  const [isStarting, setIsStarting] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [feedback, setFeedback] = useState(null)
  const [error, setError] = useState('')

  const textareaRef = useRef(null)
  const conversationEndRef = useRef(null)

  const coveredDays = useMemo(
    () => candidate.missions.map((mission) => mission.day).sort((a, b) => a - b),
    [candidate],
  )

  const transcriptCount = messages.filter((message) => message.role === 'candidate').length
  const progressValue = Math.max(0, Math.min(questionNumber, TOTAL_QUESTIONS))
  const progressPercent = Math.round((progressValue / TOTAL_QUESTIONS) * 100)
  const interviewStatus =
    view === 'results' ? 'Interview complete' : isSubmitting ? 'AI is thinking...' : 'Interview in progress'
  const currentTopic = currentQuestion || 'Technical Deep Dive'

  useEffect(() => {
    conversationEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, isSubmitting, view])

  useEffect(() => {
    if (view === 'interview' && !isSubmitting) {
      textareaRef.current?.focus()
    }
  }, [view, isSubmitting])

  async function startInterview() {
    const nextSessionId = createSessionId()
    setSessionId(nextSessionId)
    setIsStarting(true)
    setIsSubmitting(false)
    setError('')
    setFeedback(null)
    setMessages([])
    setDraft('')
    setCurrentQuestion('')
    setQuestionNumber(0)

    let response

    try {
      response = await postInterview({
        sessionId: nextSessionId,
        candidate,
      })
      const data = await readResponseBody(response)

      if (!response.ok) {
        throw new Error(data?.detail || data?.message || 'Unable to start interview.')
      }

      const initialReply = getString(data?.reply, 'Interview initialized.')
      const initialMessage = {
        id: `${nextSessionId}-ai-1`,
        role: 'interviewer',
        text: initialReply,
      }

      setMessages([initialMessage])
      setCurrentQuestion(initialReply)
      setQuestionNumber(1)

      if (data?.done) {
        setFeedback(normalizeFeedback(data.feedback))
        setView('results')
      } else {
        setView('interview')
      }
    } catch (caughtError) {
      setError(normalizeErrorMessage(caughtError, response))
      setView('landing')
    } finally {
      setIsStarting(false)
    }
  }

  async function handleSubmit(event) {
    event.preventDefault()

    const answer = draft.trim()
    if (!answer || isSubmitting || !sessionId) {
      return
    }

    setIsSubmitting(true)
    setError('')
    setDraft('')

    let response

    try {
      response = await postInterview({
        sessionId,
        message: answer,
      })
      const data = await readResponseBody(response)

      if (!response.ok) {
        throw new Error(data?.detail || data?.message || 'Unable to submit the answer.')
      }

      const candidateMessage = {
        id: `${sessionId}-candidate-${questionNumber}`,
        role: 'candidate',
        text: answer,
      }

      const interviewerReply = getString(data?.reply, 'Interview follow-up received.')
      const interviewerMessage = {
        id: `${sessionId}-ai-${questionNumber + 1}`,
        role: 'interviewer',
        text: interviewerReply,
      }

      setMessages((currentMessages) => [...currentMessages, candidateMessage, interviewerMessage])
      setCurrentQuestion(interviewerReply)
      setQuestionNumber((currentValue) => Math.min(currentValue + 1, TOTAL_QUESTIONS))

      if (data?.done) {
        setFeedback(normalizeFeedback(data.feedback))
        setView('results')
      }
    } catch (caughtError) {
      setError(normalizeErrorMessage(caughtError, response))
      setDraft(answer)
    } finally {
      setIsSubmitting(false)
    }
  }

  function resetAndLaunch() {
    setView('landing')
    startInterview()
  }

  const strengthItems = feedback?.strengths ?? []
  const gapItems = feedback?.gaps ?? []
  const nextItems = feedback?.next ?? []

  return (
    <div className="app-shell">
      <div className="ambient ambient-a" />
      <div className="ambient ambient-b" />
      <div className="ambient ambient-c" />

      <header className="topbar">
        <div>
          <div className="brand-mark">INTERVIEWOS</div>
          <div className="brand-tagline">Your curriculum. Your projects. Your interview.</div>
        </div>

        <div className="topbar-status">
          <span className={`status-chip ${view === 'results' ? 'status-chip--complete' : 'status-chip--live'}`}>
            {interviewStatus}
          </span>
        </div>
      </header>

      <main className={`screen screen--${view}`} key={view}>
        {error ? (
          <section className="error-banner" role="alert" aria-live="polite">
            <span className="error-banner__label">System notice</span>
            <p>{error}</p>
          </section>
        ) : null}

        {view === 'landing' ? (
          <section className="landing-layout">
            <div className="hero-copy panel panel--hero">
              <div className="eyebrow">AI-Powered Technical Interviewer</div>
              <h1>INTERVIEWOS</h1>
              <p className="hero-subtitle">Your curriculum. Your projects. Your interview.</p>
              <p className="hero-body">
                InterviewOS builds a personalized technical interview from your learning journey, adapts to your
                answers, and remembers what matters.
              </p>

              <div className="hero-actions">
                <button className="primary-button" onClick={startInterview} disabled={isStarting}>
                  {isStarting ? 'Launching interview...' : 'Start Technical Interview →'}
                </button>
                <span className="hero-hint">Demo candidate loaded automatically from the InterviewOS dataset.</span>
              </div>

              <div className="capability-grid">
                <article className="capability-card">
                  <span className="capability-card__label">PERSONALIZED</span>
                  <h2>Built around the candidate's completed curriculum.</h2>
                  <p>The interview adapts to the learning path, projects, and evidence already available.</p>
                </article>

                <article className="capability-card">
                  <span className="capability-card__label">ADAPTIVE</span>
                  <h2>Follow-up questions respond to strengths and weaknesses.</h2>
                  <p>Question flow stays dynamic, so every answer changes the next prompt.</p>
                </article>

                <article className="capability-card">
                  <span className="capability-card__label">MEMORY-POWERED</span>
                  <h2>Persistent candidate evidence using Breeth.</h2>
                  <p>InterviewOS keeps the interaction grounded in prior signals and interview memory.</p>
                </article>
              </div>
            </div>

            <aside className="preview-panel panel panel--preview">
              <div className="preview-panel__header">
                <span className="preview-panel__title">Interview Preview</span>
                <span className="preview-panel__pulse" />
              </div>

              <div className="preview-metric-grid">
                <div className="mini-metric">
                  <span className="mini-metric__label">Candidate</span>
                  <strong>{candidate.member.name}</strong>
                </div>
                <div className="mini-metric">
                  <span className="mini-metric__label">Role</span>
                  <strong>{candidate.member.jobRole}</strong>
                </div>
                <div className="mini-metric">
                  <span className="mini-metric__label">Experience</span>
                  <strong>{candidate.member.yearsExperience} years</strong>
                </div>
                <div className="mini-metric">
                  <span className="mini-metric__label">Curriculum</span>
                  <strong>{candidate.missions.length} covered days</strong>
                </div>
              </div>

              <div className="preview-flow">
                <div className="preview-flow__item is-active">Initialize candidate profile</div>
                <div className="preview-flow__item">Generate adaptive interview path</div>
                <div className="preview-flow__item">Capture answers and evidence</div>
                <div className="preview-flow__item">Deliver final feedback report</div>
              </div>

              <div className="preview-notes">
                <div>
                  <span className="preview-notes__label">Interview mode</span>
                  <strong>Enterprise AI cockpit</strong>
                </div>
                <div>
                  <span className="preview-notes__label">Status</span>
                  <strong>Ready for launch</strong>
                </div>
              </div>
            </aside>
          </section>
        ) : null}

        {view === 'interview' ? (
          <section className="cockpit-layout">
            <aside className="panel sidebar-panel">
              <div className="panel-heading">Candidate</div>
              <div className="candidate-card">
                <div className="candidate-avatar">SJ</div>
                <div>
                  <h2>{candidate.member.name}</h2>
                  <p>{candidate.member.jobRole}</p>
                </div>
              </div>

              <div className="sidebar-stack">
                <div className="sidebar-stat">
                  <span>Role</span>
                  <strong>{candidate.member.jobRole}</strong>
                </div>

                <div className="sidebar-stat">
                  <span>Progress</span>
                  <strong>
                    Question {Math.max(questionNumber, 1)} / {TOTAL_QUESTIONS}
                  </strong>
                  <div className="progress-track" aria-hidden="true">
                    <div className="progress-bar" style={{ width: `${progressPercent}%` }} />
                  </div>
                </div>

                <div className="sidebar-stat">
                  <span>Completed Curriculum</span>
                  <div className="day-chip-grid">
                    {coveredDays.map((day) => (
                      <span className="day-chip" key={day}>
                        Day {day}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="sidebar-stat sidebar-stat--status">
                  <span>Status</span>
                  <strong>Interview in progress</strong>
                </div>
              </div>
            </aside>

            <section className="panel conversation-panel">
              <div className="panel-heading panel-heading--split">
                <div>
                  <span className="panel-kicker">AI INTERVIEWER</span>
                  <h2>{currentQuestion ? 'Current question' : 'Awaiting interview launch'}</h2>
                </div>
                <div className="live-indicator">
                  <span className="live-indicator__dot" />
                  Adaptive session active
                </div>
              </div>

              <div className="question-card">
                <div className="question-card__label">Current topic</div>
                <p>{currentTopic}</p>
              </div>

              <div className="conversation-stream" aria-live="polite">
                {messages.map((message, index) => {
                  const isLatestInterviewer = message.role === 'interviewer' && index === messages.length - 1

                  return (
                    <article
                      key={message.id}
                      className={`message message--${message.role} ${isLatestInterviewer ? 'message--current' : ''}`}
                    >
                      <div className="message__label">
                        {message.role === 'interviewer' ? 'AI INTERVIEWER' : 'CANDIDATE'}
                      </div>
                      <p>{message.text}</p>
                    </article>
                  )
                })}

                {isSubmitting ? (
                  <article className="message message--interviewer message--thinking">
                    <div className="message__label">AI INTERVIEWER</div>
                    <div className="typing-indicator" aria-label="AI is thinking">
                      <span />
                      <span />
                      <span />
                    </div>
                    <p>AI is thinking...</p>
                  </article>
                ) : null}

                <div ref={conversationEndRef} />
              </div>

              <form className="answer-form" onSubmit={handleSubmit}>
                <label className="answer-form__label" htmlFor="candidate-answer">
                  Candidate answer
                </label>
                <textarea
                  id="candidate-answer"
                  ref={textareaRef}
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  placeholder="Explain your reasoning, architecture, trade-offs, and decisions..."
                  rows={7}
                  disabled={isSubmitting}
                />
                <div className="answer-form__footer">
                  <span className="answer-form__hint">Press submit to send the answer to the live interview engine.</span>
                  <button className="primary-button" type="submit" disabled={isSubmitting || !draft.trim()}>
                    {isSubmitting ? 'Submitting...' : 'Submit Answer →'}
                  </button>
                </div>
              </form>
            </section>

            <aside className="panel signals-panel">
              <div className="panel-heading">INTERVIEW SIGNALS</div>

              <div className="signal-list">
                <div className="signal-row">
                  <span>Current question</span>
                  <strong>{currentQuestion || 'Adaptive analysis active'}</strong>
                </div>
                <div className="signal-row">
                  <span>Interview status</span>
                  <strong>{interviewStatus}</strong>
                </div>
                <div className="signal-row">
                  <span>Question number</span>
                  <strong>
                    {Math.max(questionNumber, 1)} / {TOTAL_QUESTIONS}
                  </strong>
                </div>
                <div className="signal-row">
                  <span>Candidate role</span>
                  <strong>{candidate.member.jobRole}</strong>
                </div>
                <div className="signal-row">
                  <span>Session</span>
                  <strong>{sessionId ? `${sessionId.slice(0, 18)}…` : 'Initializing…'}</strong>
                </div>
                <div className="signal-row signal-row--placeholder">
                  <span>Analysis layer</span>
                  <strong>Adaptive analysis active</strong>
                </div>
              </div>
            </aside>
          </section>
        ) : null}

        {view === 'results' ? (
          <section className="results-layout">
            <div className="panel results-hero">
              <div className="completion-badge">
                <span className="completion-badge__ring" />
                <span>INTERVIEW COMPLETE</span>
              </div>
              <h1>Interview completed for {candidate.member.name}.</h1>
              <p className="results-summary">{feedback?.summary}</p>

              <div className="evidence-grid">
                <div className="evidence-card">
                  <span>Questions answered</span>
                  <strong>{transcriptCount}</strong>
                </div>
                <div className="evidence-card">
                  <span>Interview completed</span>
                  <strong>Yes</strong>
                </div>
                <div className="evidence-card">
                  <span>Candidate role</span>
                  <strong>{candidate.member.jobRole}</strong>
                </div>
              </div>

              <button className="primary-button primary-button--wide" onClick={resetAndLaunch}>
                Start New Interview
              </button>
            </div>

            <div className="results-columns">
              <section className="panel feedback-panel">
                <div className="panel-heading">STRENGTHS</div>
                <div className="list-grid">
                  {strengthItems.length ? (
                    strengthItems.map((item, index) => (
                      <article className="list-card list-card--success" key={`strength-${index}`}>
                        {item}
                      </article>
                    ))
                  ) : (
                    <div className="empty-state">No strengths were returned by the backend.</div>
                  )}
                </div>
              </section>

              <section className="panel feedback-panel">
                <div className="panel-heading">DEVELOPMENT GAPS</div>
                <div className="list-grid">
                  {gapItems.length ? (
                    gapItems.map((item, index) => (
                      <article className="list-card list-card--gap" key={`gap-${index}`}>
                        {item}
                      </article>
                    ))
                  ) : (
                    <div className="empty-state">No development gaps were returned by the backend.</div>
                  )}
                </div>
              </section>

              <section className="panel feedback-panel">
                <div className="panel-heading">NEXT STEPS</div>
                <div className="list-grid">
                  {nextItems.length ? (
                    nextItems.map((item, index) => (
                      <article className="list-card list-card--next" key={`next-${index}`}>
                        {item}
                      </article>
                    ))
                  ) : (
                    <div className="empty-state">No next steps were returned by the backend.</div>
                  )}
                </div>
              </section>
            </div>
          </section>
        ) : null}
      </main>
    </div>
  )
}

export default App