import os
import pytest

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
    assert b"Endeavor FDE MVP" in resp.data 