"""OpenAI calls: receipt extraction and the budgeting assistant."""

import base64
import json
import logging
from functools import lru_cache

from fastapi import HTTPException
from openai import AuthenticationError, OpenAI, OpenAIError, RateLimitError

from app.config import settings
from app.models import CATEGORIES


log = logging.getLogger(__name__)


class AIUnavailable(Exception):
    """Raised when no API key is configured or the provider call fails."""


@lru_cache
def _client() -> OpenAI:
    # Created lazily so the server starts (and non-AI routes work) without a key.
    return OpenAI(api_key=settings.openai_api_key)


def ai_enabled() -> bool:
    return bool(settings.openai_api_key)


RECEIPT_PROMPT = f"""Extract the purchase from this receipt image.
Return ONLY a JSON object with these keys:
  "merchant": store or restaurant name (string),
  "amount": final total paid, as a number without currency symbols,
  "currency": ISO 4217 code such as "USD" or "EUR",
  "category": one of {json.dumps(CATEGORIES)},
  "date": purchase date as "YYYY-MM-DD".
Only report what is printed on the receipt. If a value is not clearly shown, use null.
Never guess: item counts, quantities or line-item prices are not the total, and a
currency must not be assumed from the language or a "$" alone unless the country is clear.
The user reviews every field, and a blank field is better than a wrong one.
"""


def extract_receipt(image_bytes: bytes, mime_type: str) -> dict:
    """Return the raw dict the model produced. Raises AIUnavailable on any failure."""
    if not ai_enabled():
        raise AIUnavailable("OPENAI_API_KEY is not set")

    data_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode()}"
    try:
        response = _client().chat.completions.create(
            model=settings.openai_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": RECEIPT_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract the receipt data."},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
        )
        content = response.choices[0].message.content or ""
        return json.loads(content)
    except (OpenAIError, json.JSONDecodeError, IndexError) as exc:
        raise AIUnavailable(str(exc)) from exc


def ask_assistant(question: str, summary: dict) -> str:
    if not ai_enabled():
        raise HTTPException(status_code=503, detail="AI assistant is not configured (missing OPENAI_API_KEY)")

    recent = [
        {
            "merchant": e.merchant,
            "amount": e.amount,
            "currency": e.currency,
            "category": e.category,
            "date": e.date.isoformat(),
        }
        for e in summary["recent_expenses"]
    ]
    context = {
        "month": summary["month"],
        "monthly_budget": summary["monthly_budget"],
        "currency": summary["currency"],
        "total_spent": summary["total_spent"],
        "remaining": summary["remaining"],
        "percent_used": summary["percent_used"],
        "category_totals": summary["category_totals"],
        "category_limits": [
            {k: c[k] for k in ("category", "limit", "spent", "remaining", "status")}
            for c in summary["category_budgets"]
        ],
        "alerts": [a["message"] for a in summary["alerts"]],
        "other_currency_totals": summary["other_currency_totals"],
        "recent_expenses": recent,
    }

    try:
        completion = _client().chat.completions.create(
            model=settings.openai_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are Budget Buddy, a friendly assistant inside a personal budgeting app. "
                        "Answer clearly, briefly and practically using the user's data below. "
                        "Reply in plain text for a phone chat bubble: no markdown, no asterisks or "
                        "headings; short sentences, and simple '-' lists only when they really help. "
                        "Do not give investment, tax, or legal advice.\n\n"
                        f"User data for this month (JSON):\n{json.dumps(context)}"
                    ),
                },
                {"role": "user", "content": question},
            ],
        )
    except AuthenticationError as exc:
        log.warning("OpenAI rejected the API key: %s", exc)
        raise HTTPException(
            status_code=502, detail="OpenAI rejected the API key. Check OPENAI_API_KEY on the server."
        ) from exc
    except RateLimitError as exc:
        log.warning("OpenAI rate limit or quota: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="OpenAI usage limit reached. Check billing/quota on your OpenAI account.",
        ) from exc
    except OpenAIError as exc:
        log.warning("OpenAI request failed: %s", exc)
        raise HTTPException(status_code=502, detail="The AI service failed to respond") from exc

    return completion.choices[0].message.content or ""
