import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import create_db_and_tables
from app.routers import budget, expenses, receipts
from app.services.ai import ai_enabled

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_db_and_tables()
    settings.receipt_dir.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="Budget Buddy API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    # Browsers reject credentials with a wildcard origin; the app sends no cookies anyway.
    allow_credentials="*" not in settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(expenses.router)
app.include_router(budget.router)
app.include_router(receipts.router)


@app.get("/", tags=["meta"])
def home():
    return {"message": "Welcome to Budget Buddy!", "docs": "/docs"}


@app.get("/health", tags=["meta"])
def health():
    return {"status": "running", "ai_enabled": ai_enabled()}
