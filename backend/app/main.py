from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import Base, engine
from app.routers import exams, users, saved_exams, reminders

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="ExamPilotAI API",
    description="Backend for the ExamPilotAI government exam tracking platform",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router)
app.include_router(exams.router)
app.include_router(saved_exams.router)
app.include_router(reminders.router)


@app.get("/")
def root():
    return {"status": "ExamPilotAI API is running"}
