"""
End-to-end integration tests for Endeavor FDE MVP
Verifies all high-level requirements from the spec.
"""
from __future__ import annotations

import os
import subprocess
import time
import csv
import io
from pathlib import Path
from typing import Generator

import pytest
import requests

APP_HOST = "http://127.0.0.1:5000"
STUB_HOST = "http://127.0.0.1:5001"


@pytest.fixture(scope="session", autouse=True)
def start_stub_and_app(tmp_path_factory: pytest.TempPathFactory) -> Generator[None, None, None]:
    """Spin up the stub API and the real Flask app pointing at it."""
    # 1) Start the stub API
    stub_proc = subprocess.Popen(["python", "tests/stub_api.py"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # 2) Prepare a fresh, isolated DB path for this test session
    db_path: Path = tmp_path_factory.mktemp("e2e") / "data.db"
    os.environ["DB_PATH"] = str(db_path)

    # 3) Point the Flask app to the stub endpoints
    os.environ["EXTRACT_ENDPOINT"] = STUB_HOST + "/extraction_api"
    os.environ["MATCH_ENDPOINT"] = STUB_HOST + "/match"
    os.environ["SYNC_PARSE"] = "1"

    # 4) Start the Flask app
    app_proc = subprocess.Popen([
        "flask", "--app", "app.py", "run", "--no-reload", "--port", "5000"
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # 5) Give both services time to boot
    time.sleep(2)

    yield  # Run the tests

    # ---- Teardown ----
    stub_proc.terminate()
    app_proc.terminate()
    stub_proc.wait(timeout=5)
    app_proc.wait(timeout=5)


def test_home_page():
    r = requests.get(APP_HOST + "/")
    assert r.status_code == 200
    assert "Endeavor FDE MVP" in r.text


def test_upload_and_redirect(tmp_path):
    # create a fake PDF
    pdf = tmp_path / "Easy-1.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF")
    with pdf.open("rb") as fh:
        r = requests.post(APP_HOST + "/upload", files={"file": fh}, allow_redirects=False)
    # Expect a 302 to /review/1
    assert r.status_code == 302
    assert "/review/1" in r.headers["Location"]


def test_review_page_contains_dropdowns():
    r = requests.get(APP_HOST + "/review/1")
    assert r.status_code == 200
    # two descriptions from stub plus two <select> elements
    assert "Widget A" in r.text and "Widget B" in r.text
    assert r.text.count("<select") == 2


def test_confirm_and_csv_download():
    # pick the first choice for each match (match_id will be 1 & 2)
    payload = {"1": "0", "2": "0"}
    r = requests.post(APP_HOST + "/confirm/1", data=payload)
    assert r.headers["Content-Type"].startswith("text/csv")
    content = r.content.decode()
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    # header + 2 data rows
    assert rows[0] == ["description", "confirmed_choice"]
    assert len(rows) == 3


def test_database_persistence():
    import sqlite3

    conn = sqlite3.connect(os.environ["DB_PATH"])
    c = conn.cursor()
    # one document, two line_items, two matches
    docs = c.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    lines = c.execute("SELECT COUNT(*) FROM line_items").fetchone()[0]
    matches = c.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    assert docs == 1
    assert lines == 2
    assert matches == 2


def test_readme_includes_video_and_collaborator():
    text = Path("README.md").read_text()
    assert "loom.com" in text or "youtu.be" in text
    assert "ryan-endeavor" in text 