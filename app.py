"""
Endeavor FDE MVP
----------------
- Low-latency PDF upload & streaming parsing
- Background thread-pool for extraction & match calls
- SQLite persistence with migrations on startup
- Chunked CSV download with streaming
- Structured JSON APIs for review UI
- Env-based config & robust error handling
"""
import os
import sqlite3
import logging
import json
from typing import Any, Dict, List, Generator
from concurrent.futures import ThreadPoolExecutor

import requests
from flask import Flask, request, render_template, redirect, url_for, Response

# ---- CONFIG ----
from logging.config import dictConfig


dictConfig({
    "version": 1,
    "formatters": {"default": {
        "format": "[%(asctime)s] %(levelname)s %(name)s: %(message)s"
    }},
    "handlers": {"wsgi": {
        "class": "logging.StreamHandler",
        "formatter": "default"
    }},
    "root": {"level": "INFO", "handlers": ["wsgi"]}
})
LOG = logging.getLogger(__name__)

# External endpoints (can be overridden via env vars)
# API_BASE = os.getenv("ENDEAVOR_API", "https://api.endeavor.ai")
# EXTRACT_ENDPOINT = os.getenv("EXTRACT_ENDPOINT", f"{API_BASE}/extract")
# MATCH_ENDPOINT = os.getenv("MATCH_ENDPOINT", f"{API_BASE}/match")

# Production endpoints for the interview
# Support legacy ENDEAVOR_API for backwards compatibility with tests
API_BASE = os.getenv("ENDEAVOR_API", "")
if API_BASE:
    EXTRACT_ENDPOINT = os.getenv("EXTRACT_ENDPOINT", f"{API_BASE}/extraction_api")
    MATCH_ENDPOINT = os.getenv("MATCH_ENDPOINT", f"{API_BASE}/match")
else:
    EXTRACT_ENDPOINT = os.getenv("EXTRACT_ENDPOINT", "https://plankton-app-qajlk.ondigitalocean.app/extraction_api")
    MATCH_ENDPOINT = os.getenv("MATCH_ENDPOINT", "https://endeavor-interview-api-gzwki.ondigitalocean.app/match")

# App configuration
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "4"))
UPLOAD_FOLDER = "uploads"

# Store default path but always look up env when connecting
DEFAULT_DB_PATH = os.getenv("DB_PATH", "data.db")

def _current_db_path() -> str:
    """Return DB path from environment, falling back to default."""
    return os.getenv("DB_PATH", DEFAULT_DB_PATH)

# Allow forcing synchronous parsing (useful for integration tests)
SYNC_PARSE = os.getenv("SYNC_PARSE", "0") == "1"

# Ensure the uploads directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)


# ---- DATABASE INIT ----

def init_db() -> None:
    """Initialize the SQLite database and run migrations if necessary."""
    conn = sqlite3.connect(_current_db_path())
    conn.executescript(
        """
    CREATE TABLE IF NOT EXISTS documents (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        name         TEXT UNIQUE,
        uploaded_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS line_items (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id  INTEGER,
        description  TEXT,
        raw_index    INTEGER,
        FOREIGN KEY(document_id) REFERENCES documents(id)
    );

    CREATE TABLE IF NOT EXISTS matches (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        line_item_id  INTEGER,
        choice_json   TEXT,
        confirmed_id  INTEGER,
        FOREIGN KEY(line_item_id) REFERENCES line_items(id) ON DELETE CASCADE
    );

    -- Ensure duplicates are removed so the unique constraint can be applied when
    -- the code runs against an existing DB that already contains duplicates.
    DELETE FROM line_items
      WHERE id NOT IN (
        SELECT MIN(id) FROM line_items GROUP BY document_id, raw_index
      );

    CREATE UNIQUE INDEX IF NOT EXISTS idx_line_unique ON line_items(document_id, raw_index);
    """
    )
    conn.commit()
    conn.close()

    # Log where the database file lives for easier debugging & to ensure we
    # respect dynamic DB_PATH overrides (critical for the integration tests).
    LOG.info("Database initialised at %s", _current_db_path())


# Flask 3 removed `before_first_request`. Initialize the DB eagerly.
init_db()
LOG.info("DB initialized.")


# ---- UTILS ----

def db_conn() -> sqlite3.Connection:
    """Return a SQLite connection with Row factory enabled."""
    db_path = _current_db_path()
    # Defensive: ensure parent directory exists when a user passes a nested path.
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    # Ensure ON DELETE CASCADE works and keep referential integrity
    connection.execute("PRAGMA foreign_keys = ON;")
    # In extremely verbose logging scenarios this can be useful, but avoid
    # spamming output every query.  Toggle via LOG level if needed.
    LOG.debug("Opened SQLite connection to %s", db_path)
    return connection


def stream_csv(rows: List[Dict[str, Any]]) -> Generator[str, None, None]:
    """Yield CSV rows one at a time for streaming response."""
    yield "description,confirmed_choice\n"
    for r in rows:
        if r["confirmed_id"] is not None and r["choices"]:
            # choices is a list of {"name": "...", "score": ...} objects
            confirmed_choice = r["choices"][r["confirmed_id"]]["name"]
        else:
            confirmed_choice = ""
        # Escape quotes in CSV data
        description = r["description"].replace('"', '""')
        confirmed_choice = confirmed_choice.replace('"', '""')
        yield f'"{description}","{confirmed_choice}"\n'


# ---- ROUTES ----
@app.route("/")
def home():
    """Landing page with upload form or review table."""
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    """Handle PDF upload, save file, create document record, and queue parsing."""
    uploaded_file = request.files["file"]
    path = os.path.join(UPLOAD_FOLDER, uploaded_file.filename)
    uploaded_file.save(path)

    conn = db_conn()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO documents(name) VALUES(?)", (uploaded_file.filename,))
    conn.commit()

    doc_id = c.execute(
        "SELECT id FROM documents WHERE name=?", (uploaded_file.filename,)
    ).fetchone()["id"]

    # Parse document either synchronously or in a background thread
    if SYNC_PARSE:
        parse_and_store(doc_id, uploaded_file.filename)
    else:
        executor.submit(parse_and_store, doc_id, uploaded_file.filename)

    return redirect(url_for("review", doc_id=doc_id))


# ---- INTERNAL TASKS ----

def parse_and_store(doc_id: int, filename: str) -> None:
    """Call extract API, then persist line items for later review."""
    LOG.info("Parsing doc %s", doc_id)
    
    # Upload file to extraction API using multipart form data
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    with open(file_path, 'rb') as f:
        files = {'file': (filename, f, 'application/pdf')}
        resp = requests.post(EXTRACT_ENDPOINT, files=files)
    resp.raise_for_status()
    
    # API returns array of objects directly
    items = resp.json()
    # Convert the extraction API format to expected format
    if items and isinstance(items[0], dict) and 'description' not in items[0]:
        # API returns objects like {"Request Item": "...", "Amount": ..., ...}
        # Convert to our expected format
        formatted_items = []
        for item in items:
            request_item = item.get("Request Item", "")
            amount = item.get("Amount", "")
            # Create a description combining the key info
            description = f"{request_item} (Qty: {amount})" if amount else request_item
            formatted_items.append({"description": description})
        items = formatted_items

    conn = db_conn()
    c = conn.cursor()
    with conn:  # ensures atomic commit / rollback
        # Clear out existing data for id to avoid stale rows
        c.execute(
            "DELETE FROM matches WHERE line_item_id IN (SELECT id FROM line_items WHERE document_id=?)",
            (doc_id,))
        c.execute("DELETE FROM line_items WHERE document_id=?", (doc_id,))

        for idx, itm in enumerate(items):
            # Use UPSERT to guard against any race conditions if parse runs twice
            c.execute(
                """
                INSERT INTO line_items(document_id, description, raw_index)
                VALUES(?,?,?)
                ON CONFLICT(document_id, raw_index) DO UPDATE SET description=excluded.description
                """,
                (doc_id, itm["description"], idx))

    LOG.info("Stored %d items for doc %s", len(items), doc_id)


@app.route("/review/<int:doc_id>")
def review(doc_id: int):
    """Display review UI for a specific document."""
    conn = db_conn()
    c = conn.cursor()

    items = c.execute(
        "SELECT * FROM line_items WHERE document_id=?", (doc_id,)
    ).fetchall()

    # Ensure matches exist for each item
    for itm in items:
        if not c.execute(
            "SELECT 1 FROM matches WHERE line_item_id=?", (itm["id"],)
        ).fetchone():
            # Use GET request with query parameter for the matching API
            resp = requests.get(
                MATCH_ENDPOINT,
                params={"query": itm["description"], "limit": 5},
            )
            resp.raise_for_status()
            # Convert the API response format to match expected format
            matches = resp.json()
            choices = [{"name": m["match"], "score": m["score"]} for m in matches]
            c.execute(
                "INSERT INTO matches(line_item_id, choice_json) VALUES(?,?)",
                (itm["id"], json.dumps(choices)),
            )
    conn.commit()

    payload: List[Dict[str, Any]] = []
    for itm in items:
        m = c.execute(
            "SELECT * FROM matches WHERE line_item_id=?", (itm["id"],)
        ).fetchone()
        payload.append(
            {
                "match_id": m["id"],
                "description": itm["description"],
                "choices": json.loads(m["choice_json"]),
                "confirmed": m["confirmed_id"],
            }
        )

    return render_template(
        "index.html", REVIEW_DATA={"doc_id": doc_id, "rows": payload}
    )


@app.route("/confirm/<int:doc_id>", methods=["POST"])
def confirm(doc_id: int):
    """Persist confirmed matches and return a CSV download."""
    conn = db_conn()
    c = conn.cursor()

    # Update confirmed IDs
    for mid, sel in request.form.items():
        c.execute("UPDATE matches SET confirmed_id=? WHERE id=?", (int(sel), int(mid)))
    conn.commit()

    # Fetch data for CSV
    rows = [
        {
            "description": r["description"],
            "confirmed_id": r["confirmed_id"],
            "choices": json.loads(r["choice_json"]),
        }
        for r in c.execute(
            """
        SELECT li.description, m.confirmed_id, m.choice_json
        FROM matches m JOIN line_items li ON li.id=m.line_item_id
        WHERE li.document_id=?
        """,
            (doc_id,),
        )
    ]

    return Response(
        stream_csv(rows),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=doc_{doc_id}.csv"},
    )


if __name__ == "__main__":
    app.run(debug=True, threaded=True) 