"""Receipt file storage and data extraction (AI first, Tesseract OCR as fallback)."""

import io
import logging
import re
import uuid
from datetime import date
from pathlib import Path

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from app.config import settings
from app.models import CATEGORIES
from app.services import ai

log = logging.getLogger(__name__)

_FORMATS = {"JPEG": ("jpg", "image/jpeg"), "PNG": ("png", "image/png"), "WEBP": ("webp", "image/webp")}


def read_image(upload: UploadFile) -> tuple[bytes, str, str]:
    """Read and validate an uploaded image. Returns (bytes, extension, mime type)."""
    data = upload.file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Receipt image is larger than 10 MB")
    if not data:
        raise HTTPException(status_code=400, detail="Receipt image is empty")
    try:
        with Image.open(io.BytesIO(data)) as img:
            fmt = img.format
    except UnidentifiedImageError:
        raise HTTPException(status_code=400, detail="File is not a supported image")
    if fmt not in _FORMATS:
        raise HTTPException(status_code=400, detail="Use a JPEG, PNG or WebP image")
    ext, mime = _FORMATS[fmt]
    return data, ext, mime


def save_image(data: bytes, ext: str) -> str:
    """Store the image under a random name (never the client's filename). Returns the name."""
    settings.receipt_dir.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{ext}"
    (settings.receipt_dir / name).write_bytes(data)
    return name


def receipt_path(name: str) -> Path:
    path = (settings.receipt_dir / name).resolve()
    if path.parent != settings.receipt_dir.resolve() or not path.is_file():
        raise HTTPException(status_code=404, detail="Receipt file not found")
    return path


def delete_image(name: str | None) -> None:
    if name:
        try:
            (settings.receipt_dir / Path(name).name).unlink(missing_ok=True)
        except OSError:
            log.warning("Could not delete receipt %s", name)


# ---------- normalisation ----------

def _to_amount(value) -> float:
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    if isinstance(value, str):
        cleaned = re.sub(r"[^\d.,]", "", value)
        if "," in cleaned and "." not in cleaned:
            cleaned = cleaned.replace(",", ".")  # 12,50 -> 12.50
        cleaned = cleaned.replace(",", "")
        try:
            return round(float(cleaned), 2)
        except ValueError:
            pass
    return 0.0


def _to_date(value) -> date:
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            pass
    return date.today()


def _to_category(value) -> str:
    if isinstance(value, str):
        for cat in CATEGORIES:
            if cat.lower() == value.strip().lower():
                return cat
    return "Other"


def _to_currency(value, fallback: str) -> str:
    if isinstance(value, str) and len(value.strip()) == 3 and value.strip().isalpha():
        return value.strip().upper()
    return fallback


def _ocr(data: bytes) -> dict:
    import pytesseract

    with Image.open(io.BytesIO(data)) as img:
        gray = img.convert("L")
        gray = gray.resize((gray.width * 2, gray.height * 2))
        try:
            text = pytesseract.image_to_string(gray)
        except pytesseract.TesseractNotFoundError:
            raise HTTPException(
                status_code=503,
                detail="Receipt scanning needs OPENAI_API_KEY or a local Tesseract install",
            )
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    amounts = [float(a.replace(",", ".")) for a in re.findall(r"\d+[.,]\d{2}\b", text)]
    date_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    return {
        "merchant": lines[0] if lines else "",
        "amount": max(amounts, default=0.0),
        "date": date_match.group(1) if date_match else "",
    }


def extract(data: bytes, mime: str, fallback_currency: str) -> dict:
    """Return normalised receipt fields plus the source used ("ai" or "ocr")."""
    try:
        raw, source = ai.extract_receipt(data, mime), "ai"
    except ai.AIUnavailable as exc:
        log.info("AI extraction unavailable (%s); falling back to OCR", exc)
        raw, source = _ocr(data), "ocr"

    merchant = raw.get("merchant")
    return {
        "merchant": merchant.strip()[:200] if isinstance(merchant, str) and merchant.strip() else "Unknown merchant",
        "amount": _to_amount(raw.get("amount")),
        "currency": _to_currency(raw.get("currency"), fallback_currency),
        "category": _to_category(raw.get("category")),
        "date": _to_date(raw.get("date")),
        "source": source,
    }
