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
API_BASE = os.getenv("ENDEAVOR_API", "https://api.endeavor.ai")
EXTRACT_ENDPOINT = os.getenv("EXTRACT_ENDPOINT", f"{API_BASE}/extract")
MATCH_ENDPOINT = os.getenv("MATCH_ENDPOINT", f"{API_BASE}/match")

# App configuration
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "4"))
UPLOAD_FOLDER = "uploads"
DB_PATH = os.getenv("DB_PATH", "data.db")

# Allow forcing synchronous parsing (useful for integration tests)
SYNC_PARSE = os.getenv("SYNC_PARSE", "0") == "1"

# Ensure the uploads directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)


# ---- DATABASE INIT ----

def init_db() -> None:
    """Initialize the SQLite database and run migrations if necessary."""
    conn = sqlite3.connect(DB_PATH)
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
        FOREIGN KEY(line_item_id) REFERENCES line_items(id)
    );
    """
    )
    conn.commit()
    conn.close()


# Flask 3 removed `before_first_request`. Initialize the DB eagerly.
init_db()
LOG.info("DB initialized.")


# ---- UTILS ----

def db_conn() -> sqlite3.Connection:
    """Return a SQLite connection with Row factory enabled."""
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def stream_csv(rows: List[Dict[str, Any]]) -> Generator[str, None, None]:
    """Yield CSV rows one at a time for streaming response."""
    yield "description,confirmed_choice\n"
    for r in rows:
        confirmed_choice = r["choices"][r["confirmed_id"]] if r["confirmed_id"] is not None else ""
        yield f'"{r["description"]}","{confirmed_choice}"\n'


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
    resp = requests.post(EXTRACT_ENDPOINT, json={"documentName": filename})
    resp.raise_for_status()
    items = resp.json().get("items", [])

    conn = db_conn()
    c = conn.cursor()
    for idx, itm in enumerate(items):
        c.execute(
            "INSERT INTO line_items(document_id, description, raw_index) VALUES(?,?,?)",
            (doc_id, itm["description"], idx),
        )
    conn.commit()
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
            resp = requests.post(
                MATCH_ENDPOINT,
                json={"documentName": itm["description"], "itemIndex": itm["raw_index"]},
            )
            resp.raise_for_status()
            c.execute(
                "INSERT INTO matches(line_item_id, choice_json) VALUES(?,?)",
                (itm["id"], json.dumps(resp.json().get("choices", []))),
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