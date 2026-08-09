# InterviewOS

> **Your curriculum. Your projects. Your interview.**

InterviewOS is an AI-powered technical interviewer that turns a candidate's
actual learning journey into a personalized, multi-turn technical interview.

Instead of asking a fixed list of questions, InterviewOS combines curriculum
progress, candidate signals, answer evaluation, adaptive planning, LLM
reasoning, and persistent memory to conduct a realistic technical interview.

---

## The Problem

Completing an AI engineering program does not automatically mean a learner
can explain the systems they built.

Traditional interview preparation usually relies on:

- Static question banks
- Generic mock interviews
- No awareness of the candidate's learning history
- Little adaptation based on answer quality
- Limited actionable feedback

InterviewOS addresses this by making the **candidate's learning journey the
starting point for the interview**.

---

## What InterviewOS Does

```text
Candidate Profile
       │
       ├── Completed Missions
       ├── Attempts
       ├── Skipped Topics
       └── Learning Signals
       │
       ▼
┌─────────────────────────────┐
│     Interview Orchestrator  │
├─────────────────────────────┤
│ Planner                     │
│ Interviewer                 │
│ Answer Evaluator            │
│ Session State               │
│ Memory                      │
└──────────────┬──────────────┘
               │
        Groq / Llama 3.3
               │
               ▼
      Personalized Question
               │
               ▼
         Candidate Answer
               │
               ▼
          Evaluation
               │
               └──────► Next Question
                           │
                           ▼
                    Final Assessment

Core Features
1. Curriculum-Aware Interviews

InterviewOS reads the supplied 31-day AI Cohort curriculum and candidate
profile to determine which technical areas are relevant to the candidate.

Questions can cover areas including:

Embeddings
Vector databases
Retrieval
Prompt engineering
Chatbot APIs
Multi-agent systems
MCP
Deployment
Observability
Production AI systems
2. Adaptive Interview Intelligence

The interview is orchestrated through separate intelligence components:

Planner — selects the next interview direction
Interviewer — generates the technical question
Evaluator — evaluates the candidate's response
Orchestrator — maintains state and coordinates the interview

The system tracks interview state including:

Covered curriculum days
Covered topics
Difficulty
Previous answers
Evaluation results
Follow-up strategy
Interview completion
3. Persistent AI Memory with Breeth

InterviewOS integrates Breeth as the persistent memory layer.

Interview evidence can be stored and retrieved using candidate-specific
memory groups.

This allows the agent to retain useful interview evidence beyond a single
LLM request.

Memory is abstracted behind a provider interface, allowing deterministic
fake memory providers during testing and Breeth in the deployed system.

4. LLM-Powered Interviewing

Production inference uses:

Groq

Model: llama-3.3-70b-versatile

The application uses an LLM provider abstraction so the interview engine is
not tightly coupled to a single provider.

5. Structured Final Feedback

At the end of the interview, InterviewOS produces a structured assessment
containing:

Overall assessment
Strengths
Development gaps
Recommended next steps
Interview completion information

The goal is not simply to score the candidate, but to tell them what to
improve next.

Example Interview

A candidate's profile may indicate experience with embeddings and vector
databases while showing that observability was skipped.

InterviewOS can use that information to construct a targeted interview.

For example:

How would you generate embeddings for a large healthcare text dataset
using Sentence Transformers?

The candidate's answer is evaluated and subsequent questions can explore
related technical areas such as:

Rare medical terminology
Retrieval quality
PCA
Vector database selection
MCP integration
Production architecture
Security and scalability

At completion, the candidate receives a structured report.

Example Assessment

A completed interview can produce feedback such as:

Strengths
Strong understanding of session-based conversation management
Good authentication and authorization reasoning
Effective understanding of embeddings
Strong understanding of PCA
Ability to compare vector database architectures
Development Gaps
LLM integration and model selection
Edge cases and scalability
Security considerations
Domain-specific preprocessing
MCP performance optimization
Next Steps
Study LLM integration and model selection
Explore production scalability
Strengthen security architecture
Investigate domain-specific evaluation metrics
Practice handling rare and difficult cases
Architecture
                    ┌───────────────────────┐
                    │       React UI        │
                    │      Vite Frontend    │
                    └───────────┬───────────┘
                                │
                                │ HTTPS
                                ▼
                    ┌───────────────────────┐
                    │      FastAPI API      │
                    │   /api/interview      │
                    └───────────┬───────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │     Orchestrator      │
                    └───────────┬───────────┘
                                │
             ┌──────────────────┼──────────────────┐
             ▼                  ▼                  ▼
        ┌─────────┐       ┌───────────┐      ┌──────────┐
        │ Planner │       │ Evaluator │      │Interviewer│
        └────┬────┘       └─────┬─────┘      └────┬─────┘
             │                  │                  │
             └──────────────────┼──────────────────┘
                                ▼
                       ┌─────────────────┐
                       │ Groq / Llama    │
                       │ 3.3 70B         │
                       └─────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ Breeth Memory   │
                       └─────────────────┘
Technology Stack
Layer	Technology
Frontend	React + Vite
Backend	FastAPI
Language	Python
LLM	Groq
Model	Llama 3.3 70B Versatile
Memory	Breeth
API	REST
Testing	pytest
Frontend Deployment	Vercel
Backend Deployment	Render
API
Health
GET /health
Start Interview
POST /api/interview
Content-Type: application/json

Example:

{
  "sessionId": "demo-001",
  "candidate": {
    "...": "candidate profile"
  }
}
Continue Interview
POST /api/interview
Content-Type: application/json

Example:

{
  "sessionId": "demo-001",
  "message": "Candidate answer..."
}

The API maintains the interview state across requests.

Testing

The final local test suite contains:

64 passed

Tests cover:

Adaptive interview intelligence
Answer evaluation
Difficulty adaptation
Follow-up behavior
Curriculum coverage
Interview length
Session persistence
Final feedback
API contract
LLM providers
Provider error handling
Memory providers
Breeth integration

Run:

pytest

Expected result:

64 passed
Local Development
Backend

From the repository root:

cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --reload

Backend:

http://127.0.0.1:8000
Frontend
cd frontend
npm install
npm run dev

The frontend requires:

VITE_API_BASE_URL

Example:

VITE_API_BASE_URL=http://127.0.0.1:8000
Production Deployment
Backend

Deployed on Render:

https://interviewos-api-hezj.onrender.com
Frontend

Deployed on Vercel.

The frontend communicates with the Render API using:

VITE_API_BASE_URL
Why Breeth?

Interview memory is important because an interviewer should be able to
retain useful candidate evidence rather than treating every request as an
isolated interaction.

Breeth provides the persistent memory layer used by InterviewOS to store
and retrieve interview evidence.

The application keeps the memory integration behind a provider abstraction,
which also makes testing deterministic.

Why This Is an Agent

InterviewOS is not simply an LLM wrapper.

The interview is managed as a stateful decision process:

Observe candidate
       ↓
Evaluate answer
       ↓
Update interview state
       ↓
Consider curriculum coverage
       ↓
Retrieve relevant memory
       ↓
Plan next interaction
       ↓
Generate question
       ↓
Repeat
       ↓
Generate assessment

The LLM is one component of the system; the interview state, planning,
evaluation, memory, and orchestration determine how the interview evolves.

Hackathon Compliance

This repository includes:

Public source code
Working deployed application
AI usage documentation
Incremental development history
Automated tests
Production deployment

AI-assisted development is documented in:

PROMPTS.md

Development History

Major milestones:

42f809c  feat: initialize InterviewOS project structure
5b15ce6  groq updated
623b4d6  feat: implement adaptive interview intelligence
c763fd0  feat: integrate persistent interview memory
e5e6d72  feat: build InterviewOS interview cockpit
5e197c9  fix: add python-dotenv for deployment
Project Structure
InterviewOS/
│
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   │   ├── evaluator.py
│   │   │   ├── interviewer.py
│   │   │   ├── orchestrator.py
│   │   │   └── planner.py
│   │   │
│   │   ├── data/
│   │   │   ├── candidates.json
│   │   │   └── curriculum.json
│   │   │
│   │   ├── routers/
│   │   ├── schemas/
│   │   └── services/
│   │
│   ├── tests/
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   ├── package.json
│   └── vite.config.js
│
├── candidates.json
├── curriculum.json
├── technical-spec.md
├── PROMPTS.md
└── README.md


Team : Cognitive Crew

Built for the ABTalks Vibe Code Hackathon.

InterviewOS

Your curriculum. Your projects. Your interview.