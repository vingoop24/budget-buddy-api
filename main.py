"""Entry point so `uvicorn main:app --reload` keeps working."""

from app.main import app  # noqa: F401
