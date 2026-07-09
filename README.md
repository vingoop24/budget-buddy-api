# Budget Buddy API

FastAPI backend for Budget Buddy, an AI-powered personal finance assistant.

## Features

- Expense tracking API
- Receipt image upload
- OCR receipt extraction
- AI-powered receipt parsing
- OpenAI budgeting assistant
- Budget summary endpoint
- Spending insights endpoint
- Delete expense endpoint
- SQLite database persistence

## Tech Stack

- Python
- FastAPI
- SQLAlchemy
- SQLite
- OpenAI API
- OCR / Tesseract
- Uvicorn

## API Endpoints

- `GET /ai-insights`
- `POST /ai-assistant`
- `POST /scan-and-save-receipt`
- `DELETE /expenses/{expense_id}`
- `GET /budget-summary`

## Status

MVP in active development.

## Related Repository

Frontend: Budget Buddy Mobile
