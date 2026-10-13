import os
import pytest
import io
import json

import importlib.util
from pathlib import Path

# Explicitly load the local `app.py` file to avoid clashing with any site-packages named `app`.
_app_path = Path(__file__).resolve().parent.parent / "app.py"
spec = importlib.util.spec_from_file_location("endeavor_app", _app_path)
app_module = importlib.util.module_from_spec(spec)  # type: ignore
assert spec and spec.loader  # for mypy / type checkers
spec.loader.exec_module(app_module)  # type: ignore

app = app_module.app  # Flask application instance
init_db = app_module.init_db


@pytest.fixture(autouse=True)
def _setup_db(tmp_path, monkeypatch):
    """Isolate the DB for each test run."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DB_PATH", str(db_path))
    # Update the module-level DB_PATH used by the app module
    monkeypatch.setattr(app_module, "DB_PATH", str(db_path), raising=False)
    init_db()


@pytest.fixture()
def client():
    app.config["TESTING"] = True
    return app.test_client()


def test_home_page_loads(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Upload Purchase Order" in resp.data


def _seed_match(document_id, description="Bolt"):
    with app_module.db_conn() as conn:
        conn.execute("INSERT INTO documents(id, name) VALUES(?, ?)",
                     (document_id, f"doc-{document_id}.pdf"))
        item = conn.execute(
            "INSERT INTO line_items(document_id, description, raw_index) VALUES(?, ?, 0)",
            (document_id, description),
        ).lastrowid
        return conn.execute(
            "INSERT INTO matches(line_item_id, choice_json) VALUES(?, ?)",
            (item, json.dumps([{"name": "Steel bolt", "score": 1.0}])),
        ).lastrowid


def test_upload_requires_pdf(client):
    assert client.post("/upload").status_code == 400
    assert client.post("/upload", data={"file": (io.BytesIO(b"text"), "note.txt")}).status_code == 400


def test_upload_sanitizes_filename(client, tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "UPLOAD_FOLDER", str(tmp_path))
    monkeypatch.setattr(app_module, "SYNC_PARSE", True)
    parsed = []
    monkeypatch.setattr(app_module, "parse_and_store", lambda doc_id, filename: parsed.append(filename))
    response = client.post("/upload", data={"file": (io.BytesIO(b"%PDF"), "../../escaped.pdf")})
    assert response.status_code == 302
    assert parsed == ["escaped.pdf"]
    assert (tmp_path / "escaped.pdf").read_bytes() == b"%PDF"


@pytest.mark.parametrize("selection", ["-1", "1", "abc"])
def test_confirm_rejects_invalid_choices(client, selection):
    match = _seed_match(1)
    assert client.post("/confirm/1", data={str(match): selection}).status_code == 400
    with app_module.db_conn() as conn:
        assert conn.execute("SELECT confirmed_id FROM matches WHERE id=?", (match,)).fetchone()[0] is None


def test_confirm_does_not_modify_other_documents_or_partially_commit(client):
    own = _seed_match(1)
    other = _seed_match(2)
    response = client.post("/confirm/1", data={str(own): "0", str(other): "0"})
    assert response.status_code == 400
    with app_module.db_conn() as conn:
        assert all(row[0] is None for row in conn.execute("SELECT confirmed_id FROM matches"))


def test_confirm_exports_selected_choice(client):
    match = _seed_match(1, 'Bolt, "steel"')
    response = client.post("/confirm/1", data={str(match): "0"})
    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert b'"Bolt, ""steel""","Steel bolt"' in response.data


def test_database_initialization_creates_parent(tmp_path, monkeypatch):
    database = tmp_path / "nested" / "data.db"
    monkeypatch.setenv("DB_PATH", str(database))
    init_db()
    assert database.exists()
