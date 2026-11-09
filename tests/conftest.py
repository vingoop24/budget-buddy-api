import io
import os
import tempfile

import pytest

# Configure an isolated environment before the app (and its settings) are imported.
_tmp = tempfile.mkdtemp(prefix="budget-buddy-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["RECEIPT_DIR"] = f"{_tmp}/receipts"
os.environ["OPENAI_API_KEY"] = ""

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    SQLModel.metadata.drop_all(engine)
    with TestClient(app) as c:  # runs lifespan -> creates tables
        yield c


@pytest.fixture()
def png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (20, 20), "white").save(buf, format="PNG")
    return buf.getvalue()
