"""AdNova FastAPI 앱 진입점."""
from __future__ import annotations

from fastapi import FastAPI

from app.api import ads

app = FastAPI(title="AdNova API")

app.include_router(ads.router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
