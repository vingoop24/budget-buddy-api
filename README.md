# Budget Buddy API

FastAPI backend for Budget Buddy, an AI-powered personal finance assistant.

## Features

- Expenses: create, list (filter by month, category, search), edit, delete
- Monthly budget saved in the database, with a chosen currency
- Calendar-month summary: spent, remaining, % used, category totals, insights
- Receipt upload and viewing, stored under random file names
- Receipt scanning with OpenAI vision, falling back to local Tesseract OCR
- Scan review: extract fields without saving, flag fields that couldn't be read,
  then attach the image when the user confirms
- AI budgeting assistant that uses this month's data

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env        # then add your OPENAI_API_KEY
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

`--host 0.0.0.0` lets a phone on the same Wi-Fi reach the server.
Interactive docs: http://localhost:8000/docs

The server starts without `OPENAI_API_KEY`. Scanning then uses Tesseract
(`brew install tesseract`) and `/ai-assistant` returns 503.

## Tests

```bash
pytest
```

## Project layout

```
app/
  main.py            app, CORS, routers
  config.py          environment settings
  database.py        engine + session dependency
  models.py          Expense, Budget tables
  schemas.py         request/response models
  routers/           expenses, budget + summary + assistant, receipts
  services/          summary math, OpenAI calls, receipt storage/OCR
tests/
main.py              shim so `uvicorn main:app` works
```

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Status and whether AI is configured |
| GET | `/expenses?month=YYYY-MM&category=&q=` | List expenses, newest first |
| POST | `/expenses` | Create an expense (optional `receipt_token` attaches a scanned image) |
| GET / PATCH / DELETE | `/expenses/{id}` | Read, update, delete an expense |
| POST / GET | `/expenses/{id}/receipt` | Attach / view a receipt image |
| GET | `/categories` | Default and used categories |
| GET / PUT | `/budget` | Read / set the monthly budget |
| GET | `/summary?month=YYYY-MM` | Monthly summary (`/ai-insights` is an alias) |
| POST | `/scan-receipt` | Extract fields for review (returns `missing` + `receipt_token`) |
| POST | `/scan-and-save-receipt` | Extract and save as an expense |
| POST | `/ai-assistant` | Ask the budgeting assistant |

### Scan review flow

1. `POST /scan-receipt` reads the image and holds it for 24 hours. It returns
   the extracted fields, a `missing` list of fields it couldn't read, and a
   `receipt_token`.
2. The user corrects the fields.
3. `POST /expenses` with the corrected fields plus `receipt_token` saves the
   expense and attaches the image. Each token works once.

Only expenses in the budget's currency count toward the budget. Others are
reported in `other_currency_totals`.

## Database note

The schema changed: `date` is now a real date column and the budget is a table.
If you have an old `budget_buddy.db`, delete it before starting the server.

## Related repository

Frontend: [Budget Buddy Mobile](https://github.com/vingoop24/budget-buddy-mobile)
