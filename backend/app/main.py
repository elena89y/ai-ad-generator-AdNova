from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.database.connection import Base, engine
from app.database import models


Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AdNova API",
    description="AI Ad Generator Backend API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: 배포 시 실제 프론트엔드 주소로 제한
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok"}