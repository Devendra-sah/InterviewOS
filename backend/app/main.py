from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import interview

app = FastAPI(
    title="InterviewOS API",
    description="AI Interview Agent – POST /api/interview",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(interview.router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok"}
