# InterviewOS — AI Usage Log

## 1. Project Overview

InterviewOS is an AI-powered technical interviewer designed around the
candidate's learning journey.

The system uses:

- Candidate curriculum and mission data
- Adaptive interview planning
- LLM-based question generation
- Answer evaluation
- Persistent interview memory
- Structured final feedback
- A conversational web interface

The goal was to make the experience resemble a real technical interview
rather than a fixed questionnaire.

---

## 2. AI-Assisted Development

AI coding assistants were used throughout development for architecture,
implementation, debugging, testing, integration, and documentation.

The primary development workflow used an AI coding agent with Claude
Sonnet through Antigravity, with GitHub Copilot available as an
additional development assistant.

The development process was iterative: features were implemented,
tested, reviewed, debugged, and committed as separate milestones.

---

## 3. Initial Project Architecture

### Goal

Create the initial backend and frontend structure while preserving the
provided curriculum, candidate profiles, and technical specification.

### AI assistance

The AI assistant was instructed to:

- Create a FastAPI backend.
- Preserve the supplied candidate and curriculum JSON data.
- Implement the required `/api/interview` endpoint.
- Create request/response schemas.
- Create a session store.
- Establish the React/Vite frontend structure.
- Add initial automated tests.

### Result

The initial project structure was created and committed as:

`42f809c feat: initialize InterviewOS project structure`

---

## 4. Groq / Llama Integration

### Goal

Connect the interviewer to a real LLM while keeping the provider
replaceable for testing.

### Model

Groq:

`llama-3.3-70b-versatile`

### AI assistance

The implementation introduced an LLM provider abstraction so that
the application could use a real provider while tests could use
deterministic fake providers.

### Result

Groq became the production LLM provider and was integrated into the
interview flow.

Commit:

`5b15ce6 groq updated`

---

## 5. Adaptive Interview Intelligence

### Goal

Move beyond scripted questions and create an interview orchestration
layer capable of:

- Evaluating candidate answers
- Adjusting difficulty
- Selecting curriculum areas
- Tracking covered days and topics
- Generating follow-up questions
- Ending the interview after the required number of turns
- Producing structured final feedback

### Architecture

The intelligence layer was organized around:

- Orchestrator
- Planner
- Interviewer
- Evaluator

The orchestrator maintains the interview state and coordinates the
other components.

### Testing

The adaptive intelligence layer was covered by automated tests for:

- Answer evaluation
- Difficulty adaptation
- Weak-answer follow-ups
- Curriculum coverage
- Interview length
- Session persistence
- Final feedback
- API compatibility

Commit:

`623b4d6 feat: implement adaptive interview intelligence`

---

## 6. Persistent Interview Memory

### Goal

Integrate Breeth as a persistent memory layer for the AI interviewer.

Breeth was used to retain interview evidence so that information from
the candidate's interview could be retrieved as contextual memory.

### Memory architecture

The application uses a memory provider abstraction.

This allows:

- Fake memory during automated tests
- Breeth memory in the deployed application

Interview evidence can include information such as:

- Candidate answers
- Interview questions
- Curriculum topics
- Candidate-specific evidence

Memory is associated with the candidate/session context.

### Result

Breeth became part of the interview intelligence pipeline.

Commit:

`c763fd0 feat: integrate persistent interview memory`

---

## 7. Interview Cockpit Frontend

### Goal

Create a usable technical interview interface rather than exposing
the API directly.

The frontend provides:

- Candidate/interview context
- Current interview question
- Answer input
- Interview progress
- Completion state
- Structured final feedback

The frontend communicates with the deployed FastAPI backend.

Commit:

`e5e6d72 feat: build InterviewOS interview cockpit`

---

## 8. Testing Strategy

The project uses automated tests to protect the interview engine while
features are developed.

The final local test suite contains:

- 64 tests
- 64 passing tests

The tests cover:

### Interview intelligence

- Evaluation
- Difficulty adaptation
- Follow-up behavior
- Curriculum coverage
- Interview length
- Session persistence
- Final feedback

### API

- Initialization
- Follow-up requests
- Validation
- Health endpoint
- Completed sessions
- API contract behavior

### LLM

- Provider initialization
- Groq configuration
- Provider selection
- Error handling

### Memory

- Memory provider interface
- Fake memory provider
- Provider singleton behavior
- Breeth provider
- Evidence IDs
- Memory models

Final verification:

`64 passed`

---

## 9. Important Debugging and Recovery

During development, several integration issues were encountered.

### LLM provider dependency

The initial LLM implementation expected the OpenAI package.
The application was subsequently configured to use Groq with
`llama-3.3-70b-versatile`.

### Breeth authentication

Direct Breeth API testing initially demonstrated that the API
requires a Bearer API key.

The configured Breeth API key was then used by the application.

### Breeth network behavior

Memory writes were treated as non-blocking functionality so that a
temporary memory-network failure would not prevent an interview
response from being returned.

### Test performance

Some intelligence tests initially took a long time because real
provider calls were involved in test execution.

The test architecture was adjusted to use deterministic fake
providers for automated testing.

The final test suite completed successfully in approximately
9 seconds.

### Interrupted development change

A later development edit temporarily caused multiple tests to fail.
The incomplete changes were discarded and the repository was restored
to the last known-good commit.

The test suite subsequently returned to:

`64 passed`

This recovery preserved the stable production implementation.

---

## 10. Deployment

### Backend

The FastAPI backend was deployed to Render.

Production API:

`https://interviewos-api-hezj.onrender.com`

The production `/api/interview` endpoint was tested successfully.

### Frontend

The React/Vite frontend was deployed to Vercel.

The frontend uses:

`VITE_API_BASE_URL`

to communicate with the deployed backend.

### Production verification

The complete public interview flow was tested:

1. Start interview
2. Generate AI question
3. Submit candidate answer
4. Generate subsequent questions
5. Complete interview
6. Generate structured feedback

---

## 11. AI Interview Demonstration

A complete interview was conducted using the deployed application.

The interview generated 8 questions and produced structured feedback
for the synthetic candidate Sarah Johnson, a Senior Data Engineer.

The final report included:

- Overall score
- Questions answered
- Candidate role
- Strengths
- Development gaps
- Next steps

The feedback identified areas including:

- Session-based conversation management
- Authentication and authorization
- Sentence Transformer embeddings
- PCA
- MCP
- Vector database selection
- LLM integration
- Scalability
- Healthcare data considerations

---

## 12. Development Principles

The implementation prioritized:

- Small incremental changes
- Automated testing
- Provider abstractions
- Deterministic tests
- Clear separation between interview components
- Production/development configuration separation
- Persistent memory
- API compatibility
- Deployment verification

Git commits were used to separate major development milestones.

---

## 13. AI Tools Used

### Antigravity + Claude Sonnet

Used for:

- Architecture
- Code generation
- Refactoring
- Debugging
- Test generation
- Integration work
- Deployment troubleshooting
- Documentation

### GitHub Copilot

Available as an additional AI-assisted development tool for
implementation and debugging.

### Groq

Used as the production LLM inference provider with:

`llama-3.3-70b-versatile`

### Breeth

Used as the persistent memory layer for the interview agent.

---

## 14. Final Verification

At the final development checkpoint:

- Git working tree: clean
- Backend tests: 64 passed
- Frontend production build: successful
- Backend deployment: operational
- Frontend deployment: operational
- End-to-end interview: completed
- Structured feedback: generated
- Persistent memory integration: operational