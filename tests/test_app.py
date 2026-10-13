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


def _upload_for_parse(client, tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, 'UPLOAD_FOLDER', str(tmp_path))
    monkeypatch.setattr(app_module, 'SYNC_PARSE', True)
    return client.post('/upload', data={'file': (io.BytesIO(b'%PDF'), 'state.pdf')})


def test_extraction_timeout_is_persisted_and_visible(client, tmp_path, monkeypatch):
    import requests
    calls = []
    def timeout(*args, **kwargs):
        calls.append(kwargs['timeout'])
        raise requests.Timeout('provider secret response must not be shown')
    monkeypatch.setattr(app_module.requests, 'post', timeout)
    assert _upload_for_parse(client, tmp_path, monkeypatch).status_code == 302
    status = client.get('/status/1').json
    assert status['status'] == 'failed'
    assert 'timed out' in status['error']
    assert 'secret' not in status['error']
    assert calls == [app_module.PROVIDER_TIMEOUT]
    review = client.get('/review/1')
    assert review.status_code == 502 and b'Document processing failed' in review.data
    assert client.post('/confirm/1').status_code == 409
    init_db()
    assert client.get('/status/1').json == status


def test_processing_has_a_status_and_rejects_export(client, tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, 'UPLOAD_FOLDER', str(tmp_path))
    monkeypatch.setattr(app_module, 'SYNC_PARSE', False)
    monkeypatch.setattr(app_module.executor, 'submit', lambda *args: None)
    client.post('/upload', data={'file': (io.BytesIO(b'%PDF'), 'queued.pdf')})
    assert client.get('/status/1').json['status'] == 'queued'
    assert client.get('/review/1').status_code == 202
    assert b'in progress' in client.get('/review/1').data
    assert client.post('/confirm/1').status_code == 409
    init_db()
    assert client.get('/status/1').json['status'] == 'failed'
    assert 'interrupted' in client.get('/status/1').json['error']


@pytest.mark.parametrize('payload', [{'error': 'not items'}, [None], [{'other': 'not description'}]])
def test_malformed_extraction_does_not_become_ready(client, tmp_path, monkeypatch, payload):
    class Response:
        def raise_for_status(self): pass
        def json(self): return payload
    monkeypatch.setattr(app_module.requests, 'post', lambda *args, **kwargs: Response())
    _upload_for_parse(client, tmp_path, monkeypatch)
    assert client.get('/status/1').json['status'] == 'failed'
    with app_module.db_conn() as conn:
        assert conn.execute('SELECT COUNT(*) FROM line_items').fetchone()[0] == 0


def test_missing_document_returns_not_found(client):
    assert client.get('/status/999').status_code == 404
    assert client.get('/review/999').status_code == 404
