import { useEffect, useMemo, useRef, useState } from 'react'
import {
  candidateOptions,
  getCandidateHighlights,
  getCandidateMeta,
  getCandidateMilestoneCount,
} from './candidates'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
const TOTAL_QUESTIONS = 10

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

function ProgressIndicator({ questionNumber, totalQuestions, compact = false }) {
  const percent = Math.round((Math.max(0, Math.min(questionNumber, totalQuestions)) / totalQuestions) * 100)

  return (
    <div className={`progress-indicator${compact ? ' progress-indicator--compact' : ''}`}>
      <div className="progress-indicator__text">
        Question {questionNumber} of {totalQuestions}
      </div>
      <div className="progress-indicator__bar" aria-hidden="true">
        <span style={{ width: `${percent}%` }} />
      </div>
      <div className="progress-indicator__percent">{percent}%</div>
    </div>
  )
}

function CandidateCard({ candidate, selected, onSelect }) {
  const initials = candidate.member.name
    .split(' ')
    .map((part) => part[0])
    .slice(0, 2)
    .join('')

  return (
    <button
      type="button"
      className={`candidate-card ${selected ? 'candidate-card--selected' : ''}`}
      onClick={() => onSelect(candidate)}
      aria-pressed={selected}
    >
      <div className="candidate-card__avatar" aria-hidden="true">
        {initials}
      </div>
      <div className="candidate-card__body">
        <div className="candidate-card__header">
          <div>
            <div className="candidate-card__name">{candidate.member.name}</div>
            <div className="candidate-card__role">{candidate.member.jobRole}</div>
          </div>
          <span className="candidate-card__select-label">{selected ? 'Selected' : 'Select'}</span>
        </div>
        <div className="candidate-card__meta">{getCandidateMeta(candidate)}</div>
        <div className="candidate-card__milestones">{getCandidateMilestoneCount(candidate)} curriculum milestones</div>
        <div className="candidate-card__topics">{getCandidateHighlights(candidate).join(' · ')}</div>
      </div>
    </button>
  )
}

function ExitDialog({ open, onStay, onExit }) {
  useEffect(() => {
    if (!open) {
      return undefined
    }

    const onKeyDown = (event) => {
      if (event.key === 'Escape') {
        onStay()
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, onStay])

  if (!open) {
    return null
  }

  return (
    <div className="dialog-backdrop" role="presentation" onClick={onStay}>
      <div
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="exit-dialog-title"
        aria-describedby="exit-dialog-description"
        onClick={(event) => event.stopPropagation()}
      >
        <h2 id="exit-dialog-title">Leave this interview?</h2>
        <p id="exit-dialog-description">
          Your current session will remain on the server, but this screen will return to candidate selection.
        </p>
        <div className="dialog__actions">
          <button type="button" className="button button--secondary" onClick={onStay}>
            Stay
          </button>
          <button type="button" className="button button--danger" onClick={onExit}>
            Exit
          </button>
        </div>
      </div>
    </div>
  )
}

function Transcript({ messages }) {
  if (!messages.length) {
    return null
  }

  return (
    <details className="transcript">
      <summary>Transcript ({messages.length} messages)</summary>
      <div className="transcript__list">
        {messages.map((message) => (
          <div key={message.id} className={`transcript__item transcript__item--${message.role}`}>
            <div className="transcript__role">{message.role === 'interviewer' ? 'Interviewer' : 'Candidate'}</div>
            <div className="transcript__text">{message.text}</div>
          </div>
        ))}
      </div>
    </details>
  )
}

function ResultsReport({ candidate, feedback, transcriptCount, onStartAnother }) {
  return (
    <main className="screen screen--results">
      <header className="app-header app-header--results">
        <div>
          <div className="app-header__brand">INTERVIEWOS</div>
          <div className="app-header__subtitle">Technical Interview Platform</div>
        </div>
        <div className="status-pill status-pill--success">Interview complete</div>
      </header>

      <section className="results-report">
        <div className="results-report__header">
          <div>
            <div className="results-report__eyebrow">Interview complete</div>
            <h1>{candidate.member.name}</h1>
            <p>{candidate.member.jobRole}</p>
          </div>
          <div className="results-report__meta">
            <div className="results-report__meta-label">Assessment score</div>
            <div className="results-report__meta-value">Not exposed by API</div>
          </div>
        </div>

        <div className="results-summary">
          <div className="section-heading">Performance summary</div>
          <p>{feedback.summary}</p>
        </div>

        <div className="results-grid">
          <section className="results-section">
            <div className="section-heading">Strengths</div>
            <ul>
              {feedback.strengths.length ? (
                feedback.strengths.map((item, index) => <li key={`strength-${index}`}>{item}</li>)
              ) : (
                <li>No strengths were returned by the backend.</li>
              )}
            </ul>
          </section>

          <section className="results-section">
            <div className="section-heading">Development areas</div>
            <ul>
              {feedback.gaps.length ? (
                feedback.gaps.map((item, index) => <li key={`gap-${index}`}>{item}</li>)
              ) : (
                <li>No development areas were returned by the backend.</li>
              )}
            </ul>
          </section>

          <section className="results-section results-section--full">
            <div className="section-heading">Recommended next steps</div>
            <ul>
              {feedback.next.length ? (
                feedback.next.map((item, index) => <li key={`next-${index}`}>{item}</li>)
              ) : (
                <li>No next steps were returned by the backend.</li>
              )}
            </ul>
          </section>

          <section className="results-section results-section--full results-section--subtle">
            <div className="section-heading">Interview evidence</div>
            <div className="evidence-row">
              <span>Questions answered</span>
              <strong>{transcriptCount}</strong>
            </div>
            <div className="evidence-row">
              <span>Interview completed</span>
              <strong>Yes</strong>
            </div>
            <div className="evidence-row">
              <span>Candidate role</span>
              <strong>{candidate.member.jobRole}</strong>
            </div>
          </section>
        </div>

        <div className="results-actions">
          <button type="button" className="button button--primary" onClick={onStartAnother}>
            Start another interview
          </button>
        </div>
      </section>
    </main>
  )
}

function App() {
  const [view, setView] = useState('landing')
  const [selectedCandidate, setSelectedCandidate] = useState(null)
  const [activeCandidate, setActiveCandidate] = useState(null)
  const [sessionId, setSessionId] = useState('')
  const [messages, setMessages] = useState([])
  const [currentQuestion, setCurrentQuestion] = useState('')
  const [questionNumber, setQuestionNumber] = useState(0)
  const [draft, setDraft] = useState('')
  const [isStarting, setIsStarting] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [feedback, setFeedback] = useState(null)
  const [error, setError] = useState('')
  const [showExitDialog, setShowExitDialog] = useState(false)

  const textareaRef = useRef(null)
  const conversationEndRef = useRef(null)

  const transcriptCount = messages.filter((message) => message.role === 'candidate').length
  const milestonesCount = activeCandidate ? getCandidateMilestoneCount(activeCandidate) : 0
  const progressPercent = Math.round((Math.max(0, Math.min(questionNumber, TOTAL_QUESTIONS)) / TOTAL_QUESTIONS) * 100)
  const completedTopics = useMemo(
    () => (activeCandidate ? getCandidateHighlights(activeCandidate, 4) : []),
    [activeCandidate],
  )

  useEffect(() => {
    conversationEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, isSubmitting, view])

  useEffect(() => {
    if (view === 'interview' && !isSubmitting) {
      textareaRef.current?.focus()
    }
  }, [view, isSubmitting])

  function resetToSelection({ clearSelection = true } = {}) {
    setView('landing')
    setSessionId('')
    setMessages([])
    setCurrentQuestion('')
    setQuestionNumber(0)
    setDraft('')
    setIsStarting(false)
    setIsSubmitting(false)
    setFeedback(null)
    setError('')
    setShowExitDialog(false)
    setActiveCandidate(null)
    if (clearSelection) {
      setSelectedCandidate(null)
    }
  }

  async function startInterview() {
    if (!selectedCandidate) {
      setError('Select a candidate to begin the interview.')
      return
    }

    const nextSessionId = createSessionId()
    setActiveCandidate(selectedCandidate)
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
        candidate: selectedCandidate,
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
      setView(data?.done ? 'results' : 'interview')

      if (data?.done) {
        setFeedback(normalizeFeedback(data.feedback))
      }
    } catch (caughtError) {
      setError(normalizeErrorMessage(caughtError, response))
      resetToSelection({ clearSelection: false })
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

  function handleStartAnother() {
    resetToSelection()
  }

  if (view === 'results' && activeCandidate && feedback) {
    return (
      <ResultsReport
        candidate={activeCandidate}
        feedback={feedback}
        transcriptCount={transcriptCount}
        onStartAnother={handleStartAnother}
      />
    )
  }

  return (
    <div className="app-shell">
      <main className={`screen screen--${view}`}>
        <header className="app-header">
          <div>
            <div className="app-header__brand">INTERVIEWOS</div>
            <div className="app-header__subtitle">Technical Interview Platform</div>
          </div>
          <div className="status-pill">System operational</div>
        </header>

        {error ? (
          <div className="inline-alert" role="alert" aria-live="polite">
            {error}
          </div>
        ) : null}

        {view === 'landing' ? (
          <section className="landing-view">
            <div className="landing-intro panel panel--compact">
              <div className="landing-intro__copy">
                <div className="section-kicker">Technical Interview</div>
                <h1>
                  Evaluate technical depth using the candidate&apos;s learning history, projects and demonstrated evidence.
                </h1>
                <p>
                  Select a candidate to launch a structured technical interview powered by the existing InterviewOS
                  backend.
                </p>
              </div>

              <div className="facts-row" aria-label="Product facts">
                <div>Adaptive questioning</div>
                <div>Persistent candidate memory</div>
                <div>Evidence-based evaluation</div>
              </div>
            </div>

            <section className="selector-panel panel panel--compact">
              <div className="selector-panel__header">
                <div>
                  <div className="section-kicker">Select candidate</div>
                  <h2>Choose one candidate to interview</h2>
                </div>
                <div className="selector-panel__count">{candidateOptions.length} candidates</div>
              </div>

              <div className="candidate-grid">
                {candidateOptions.map((candidate) => (
                  <CandidateCard
                    key={candidate.member.id}
                    candidate={candidate}
                    selected={selectedCandidate?.member.id === candidate.member.id}
                    onSelect={setSelectedCandidate}
                  />
                ))}
              </div>

              <div className="landing-actions">
                <button
                  type="button"
                  className="button button--primary"
                  onClick={startInterview}
                  disabled={isStarting || !selectedCandidate}
                >
                  {isStarting ? 'Starting interview...' : 'Start interview'}
                </button>
                {selectedCandidate ? (
                  <div className="selected-summary">
                    Selected: {selectedCandidate.member.name} · {selectedCandidate.member.jobRole}
                  </div>
                ) : (
                  <div className="selected-summary selected-summary--muted">Select one candidate to continue.</div>
                )}
              </div>
            </section>
          </section>
        ) : null}

        {view === 'interview' && activeCandidate ? (
          <section className="interview-shell">
            <header className="interview-header panel panel--compact">
              <button
                type="button"
                className="button button--ghost"
                onClick={() => setShowExitDialog(true)}
                aria-label="Exit interview"
              >
                ← Exit interview
              </button>

              <div className="interview-header__center">
                <div className="app-header__brand">INTERVIEWOS</div>
                <div className="interview-header__title">
                  Technical Interview · {activeCandidate.member.name} · {activeCandidate.member.jobRole}
                </div>
              </div>

              <div className="interview-header__status">
                <div className="status-pill status-pill--live">● Live</div>
                <div className="question-counter">
                  Question {questionNumber} of {TOTAL_QUESTIONS}
                </div>
              </div>
            </header>

            <div className="interview-layout">
              <main className="interview-main">
                <section className="panel panel--compact candidate-summary">
                  <div className="section-kicker">Candidate</div>
                  <h1>{activeCandidate.member.name}</h1>
                  <p>{activeCandidate.member.jobRole}</p>
                </section>

                <section className="panel panel--compact question-panel" aria-live="polite">
                  {isSubmitting ? (
                    <div className="question-panel__loading">
                      <div className="loading-spinner" aria-hidden="true">
                        <span />
                        <span />
                        <span />
                      </div>
                      <div>
                        <div className="question-panel__loading-title">Analyzing response...</div>
                        <div className="question-panel__loading-subtitle">Generating next question...</div>
                      </div>
                    </div>
                  ) : (
                    <>
                      <div className="section-kicker">Current question</div>
                      <div className="question-panel__question">{currentQuestion}</div>
                    </>
                  )}
                </section>

                <section className="panel panel--compact response-panel">
                  <form onSubmit={handleSubmit}>
                    <label className="field-label" htmlFor="candidate-response">
                      Candidate response
                    </label>
                    <textarea
                      id="candidate-response"
                      ref={textareaRef}
                      value={draft}
                      onChange={(event) => setDraft(event.target.value)}
                      placeholder="Explain your reasoning, architecture, trade-offs, and decisions..."
                      rows={8}
                      disabled={isSubmitting}
                    />
                    <div className="response-actions">
                      <button className="button button--primary" type="submit" disabled={isSubmitting || !draft.trim()}>
                        {isSubmitting ? 'Submitting...' : 'Submit answer'}
                      </button>
                    </div>
                  </form>
                </section>

                <Transcript messages={messages} />
              </main>

              <aside className="interview-sidebar panel panel--compact">
                <div className="sidebar-block">
                  <div className="section-kicker">Interview</div>
                  <div className="sidebar-metric">
                    <span>Question</span>
                    <strong>
                      {questionNumber} / {TOTAL_QUESTIONS}
                    </strong>
                  </div>
                  <ProgressIndicator questionNumber={questionNumber} totalQuestions={TOTAL_QUESTIONS} compact />
                </div>

                <div className="sidebar-block">
                  <div className="section-kicker">Candidate</div>
                  <div className="sidebar-text strong">{activeCandidate.member.jobRole}</div>
                  <div className="sidebar-text">{getCandidateMeta(activeCandidate)}</div>
                </div>

                <div className="sidebar-block">
                  <div className="section-kicker">Curriculum</div>
                  <div className="sidebar-text strong">{milestonesCount} completed milestones</div>
                  {completedTopics.length ? (
                    <ul className="sidebar-list">
                      {completedTopics.map((topic) => (
                        <li key={topic}>{topic}</li>
                      ))}
                    </ul>
                  ) : null}
                </div>

                <div className="sidebar-block">
                  <div className="section-kicker">Session</div>
                  <div className="sidebar-text strong">{sessionId ? `${sessionId.slice(0, 16)}…` : 'Initializing…'}</div>
                  <div className="sidebar-text">Adaptive session active</div>
                </div>
              </aside>
            </div>
          </section>
        ) : null}
      </main>

      <ExitDialog open={showExitDialog} onStay={() => setShowExitDialog(false)} onExit={() => resetToSelection()} />
    </div>
  )
}

export default App