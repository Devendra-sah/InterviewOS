# InterviewOS

AI Interview Agent — Hackathon submission.

## Structure
```
InterviewOS/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app
│   │   ├── routers/
│   │   │   └── interview.py     # POST /api/interview
│   │   ├── schemas/
│   │   │   ├── candidate.py     # CandidateRecord + sub-models
│   │   │   └── interview.py     # InterviewRequest / InterviewResponse
│   │   ├── services/
│   │   │   └── session_store.py # In-memory session state
│   │   └── data/
│   │       ├── candidates.json
│   │       └── curriculum.json
│   ├── tests/
│   │   └── test_interview.py
│   ├── requirements.txt
│   └── pytest.ini
└── frontend/                    # Vite/React scaffold (UI deferred)
    ├── package.json
    └── vite.config.js
```

## Backend setup
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Run server
```bash
uvicorn app.main:app --reload
```

## Run tests
```bash
pytest tests/ -v
```
