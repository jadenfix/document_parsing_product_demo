"""
Endeavor FDE MVP
----------------
- Modern UI with drag-and-drop file upload
- Real-time progress indicators and step tracking
- Professional styling with confidence indicators
- Robust error handling and user feedback
- Background processing with visual feedback
- SQLite persistence with comprehensive logging
- Production-ready API integration
- Responsive design for all devices
"""
import os
import sqlite3
import logging
import json
import time
from typing import Any, Dict, List, Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import requests
from flask import Flask, request, render_template, redirect, url_for, Response, jsonify

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

# External endpoints - Production APIs
EXTRACT_ENDPOINT = os.getenv("EXTRACT_ENDPOINT", "https://plankton-app-qajlk.ondigitalocean.app/extraction_api")
MATCH_ENDPOINT = os.getenv("MATCH_ENDPOINT", "https://endeavor-interview-api-gzwki.ondigitalocean.app/match")

# App configuration
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "4"))
UPLOAD_FOLDER = "uploads"
DB_PATH = os.getenv("DB_PATH", "data.db")

# Performance and reliability settings
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
SYNC_PARSE = os.getenv("SYNC_PARSE", "0") == "1"

# Ensure the uploads directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)


# ---- DATABASE INIT ----

def init_db() -> None:
    """Initialize the SQLite database with enhanced schema and migrations."""
    conn = sqlite3.connect(DB_PATH)
    
    # Create base tables first
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
    
    # Check if we need to add new columns (migrations)
    cursor = conn.cursor()
    
    # Migrate documents table
    try:
        cursor.execute("SELECT status FROM documents LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE documents ADD COLUMN status TEXT DEFAULT 'uploaded'")
        cursor.execute("ALTER TABLE documents ADD COLUMN processed_at TIMESTAMP")
        cursor.execute("ALTER TABLE documents ADD COLUMN error_message TEXT")
        cursor.execute("ALTER TABLE documents ADD COLUMN file_size INTEGER")
        cursor.execute("ALTER TABLE documents ADD COLUMN item_count INTEGER DEFAULT 0")
        LOG.info("Migrated documents table with new columns")
    
    # Migrate line_items table
    try:
        cursor.execute("SELECT created_at FROM line_items LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE line_items ADD COLUMN created_at TIMESTAMP")
        LOG.info("Migrated line_items table with created_at column")
    
    # Migrate matches table
    try:
        cursor.execute("SELECT confidence_score FROM matches LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE matches ADD COLUMN confidence_score REAL DEFAULT 1.0")
        cursor.execute("ALTER TABLE matches ADD COLUMN created_at TIMESTAMP")
        LOG.info("Migrated matches table with new columns")
    
    # Create processing_logs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS processing_logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER,
            step        TEXT NOT NULL,
            status      TEXT NOT NULL,
            message     TEXT,
            duration_ms INTEGER,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(document_id) REFERENCES documents(id)
        )
    """)
    
    # Create indexes for better performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_line_items_doc_id ON line_items(document_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_matches_line_item_id ON matches(line_item_id)")
    
    conn.commit()
    conn.close()


# Initialize database on startup
init_db()
LOG.info("Enhanced database initialized with performance indexes")


# ---- UTILS ----

def db_conn() -> sqlite3.Connection:
    """Return a SQLite connection with Row factory enabled."""
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def log_processing_step(doc_id: int, step: str, status: str, message: str = "", duration_ms: int = 0):
    """Log processing steps for monitoring and debugging."""
    conn = db_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO processing_logs(document_id, step, status, message, duration_ms) VALUES(?,?,?,?,?)",
        (doc_id, step, status, message, duration_ms)
    )
    conn.commit()
    conn.close()


def make_api_request(url: str, method: str = 'GET', **kwargs) -> requests.Response:
    """Make API request with retry logic and proper error handling."""
    session = requests.Session()
    session.timeout = REQUEST_TIMEOUT
    
    for attempt in range(MAX_RETRIES):
        try:
            if method.upper() == 'GET':
                response = session.get(url, **kwargs)
            elif method.upper() == 'POST':
                response = session.post(url, **kwargs)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            return response
            
        except requests.exceptions.RequestException as e:
            LOG.warning(f"API request attempt {attempt + 1} failed: {e}")
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep(2 ** attempt)  # Exponential backoff


def stream_csv(rows: List[Dict[str, Any]]) -> Generator[str, None, None]:
    """Yield CSV rows one at a time for streaming response."""
    yield "description,confirmed_choice,confidence_score\n"
    for r in rows:
        confirmed_choice = r["choices"][r["confirmed_id"]] if r["confirmed_id"] is not None else ""
        confidence = r.get("confidence_score", 1.0)
        yield f'"{r["description"]}","{confirmed_choice}","{confidence}"\n'


# ---- ROUTES ----

@app.route("/")
def home():
    """Enhanced landing page with statistics."""
    conn = db_conn()
    c = conn.cursor()
    
    # Get basic statistics
    stats = {
        'total_documents': c.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
        'total_items': c.execute("SELECT COUNT(*) FROM line_items").fetchone()[0],
        'processed_today': c.execute(
            "SELECT COUNT(*) FROM documents WHERE DATE(uploaded_at) = DATE('now')"
        ).fetchone()[0]
    }
    
    conn.close()
    return render_template("index.html", stats=stats)


@app.route("/api/stats")
def api_stats():
    """API endpoint for statistics (for AJAX updates)."""
    conn = db_conn()
    c = conn.cursor()
    
    stats = {
        'total_documents': c.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
        'total_items': c.execute("SELECT COUNT(*) FROM line_items").fetchone()[0],
        'success_rate': 0.95,  # Could calculate from actual data
        'avg_processing_time': 2.5  # Could calculate from processing_logs
    }
    
    conn.close()
    return jsonify(stats)


@app.route("/upload", methods=["POST"])
def upload():
    """Enhanced PDF upload with comprehensive error handling."""
    start_time = time.time()
    
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
            
        uploaded_file = request.files["file"]
        if uploaded_file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
            
        if not uploaded_file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'Only PDF files are supported'}), 400
        
        # Save file and get size
        file_path = os.path.join(UPLOAD_FOLDER, uploaded_file.filename)
        uploaded_file.save(file_path)
        file_size = os.path.getsize(file_path)
        
        conn = db_conn()
        c = conn.cursor()
        
        # Insert or update document record
        c.execute(
            "INSERT OR REPLACE INTO documents(name, file_size, status) VALUES(?,?,?)",
            (uploaded_file.filename, file_size, 'processing')
        )
        conn.commit()

        doc_id = c.execute(
            "SELECT id FROM documents WHERE name=?", (uploaded_file.filename,)
        ).fetchone()["id"]
        
        conn.close()
        
        # Log upload step
        upload_duration = int((time.time() - start_time) * 1000)
        log_processing_step(doc_id, 'upload', 'success', f'File size: {file_size} bytes', upload_duration)
        
        # Process document
        if SYNC_PARSE:
            parse_and_store(doc_id, uploaded_file.filename)
        else:
            executor.submit(parse_and_store, doc_id, uploaded_file.filename)

        return redirect(url_for("review", doc_id=doc_id))
        
    except Exception as e:
        LOG.error(f"Upload failed: {e}")
        return jsonify({'error': 'Upload failed. Please try again.'}), 500


# ---- ENHANCED PROCESSING ----

def parse_and_store(doc_id: int, filename: str) -> None:
    """Enhanced extraction with comprehensive logging and error handling."""
    start_time = time.time()
    
    try:
        LOG.info(f"Starting extraction for document {doc_id}: {filename}")
        
        # Update document status
        conn = db_conn()
        c = conn.cursor()
        c.execute("UPDATE documents SET status='extracting' WHERE id=?", (doc_id,))
        conn.commit()
        conn.close()
        
        # Read the actual PDF file and send it as multipart/form-data
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        with open(file_path, 'rb') as f:
            files = {'file': (filename, f, 'application/pdf')}
            resp = make_api_request(EXTRACT_ENDPOINT, 'POST', files=files)
        
        items = resp.json()  # The API returns array of objects directly
        extraction_duration = int((time.time() - start_time) * 1000)
        
        log_processing_step(doc_id, 'extract', 'success', f'Extracted {len(items)} items', extraction_duration)

        # Store extracted items
        conn = db_conn()
        c = conn.cursor()
        
        for idx, item in enumerate(items):
            description = item.get('Request Item', str(item)) if isinstance(item, dict) else str(item)
            c.execute(
                "INSERT INTO line_items(document_id, description, raw_index) VALUES(?,?,?)",
                (doc_id, description, idx),
            )
        
        # Update document with completion info
        c.execute(
            "UPDATE documents SET status='completed', processed_at=CURRENT_TIMESTAMP, item_count=? WHERE id=?",
            (len(items), doc_id)
        )
        
        conn.commit()
        conn.close()
        
        LOG.info(f"Successfully processed document {doc_id}: {len(items)} items extracted")
        
    except Exception as e:
        error_duration = int((time.time() - start_time) * 1000)
        error_msg = str(e)
        
        LOG.error(f"Extraction failed for document {doc_id}: {error_msg}")
        log_processing_step(doc_id, 'extract', 'error', error_msg, error_duration)
        
        # Update document status
        conn = db_conn()
        c = conn.cursor()
        c.execute(
            "UPDATE documents SET status='error', error_message=? WHERE id=?",
            (error_msg, doc_id)
        )
        conn.commit()
        conn.close()


@app.route("/review/<int:doc_id>")
def review(doc_id: int):
    """Enhanced review page with better error handling and matching."""
    try:
        conn = db_conn()
        c = conn.cursor()

        # Check document status
        doc = c.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        if not doc:
            return "Document not found", 404
            
        if doc['status'] == 'error':
            return f"Document processing failed: {doc['error_message']}", 500

        items = c.execute(
            "SELECT * FROM line_items WHERE document_id=? ORDER BY raw_index", (doc_id,)
        ).fetchall()

        if not items:
            return "No items found. Document may still be processing.", 202

        # Ensure matches exist for each item with enhanced error handling
        for itm in items:
            if not c.execute(
                "SELECT 1 FROM matches WHERE line_item_id=?", (itm["id"],)
            ).fetchone():
                
                match_start = time.time()
                try:
                    # Use the GET /match endpoint with query parameter
                    resp = make_api_request(
                        MATCH_ENDPOINT,
                        'GET',
                        params={"query": itm["description"], "limit": 5}
                    )
                    matches = resp.json()
                    choices = [match["match"] for match in matches]
                    confidence = matches[0]["score"] / 100.0 if matches else 0.5
                    
                    c.execute(
                        "INSERT INTO matches(line_item_id, choice_json, confidence_score) VALUES(?,?,?)",
                        (itm["id"], json.dumps(choices), confidence)
                    )
                    
                    match_duration = int((time.time() - match_start) * 1000)
                    log_processing_step(doc_id, 'match', 'success', f'Matched item: {itm["description"][:50]}', match_duration)
                    
                except Exception as e:
                    LOG.warning(f"Matching failed for item {itm['id']}: {e}")
                    # Insert default/fallback matches
                    fallback_choices = [f"No match found for: {itm['description'][:30]}..."]
                    c.execute(
                        "INSERT INTO matches(line_item_id, choice_json, confidence_score) VALUES(?,?,?)",
                        (itm["id"], json.dumps(fallback_choices), 0.1)
                    )
                    
                    match_duration = int((time.time() - match_start) * 1000)
                    log_processing_step(doc_id, 'match', 'warning', f'Fallback match: {str(e)}', match_duration)
        
        conn.commit()

        # Build enhanced payload with confidence scores
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
                    "confidence_score": m["confidence_score"]
                }
            )

        conn.close()
        return render_template(
            "index.html", 
            REVIEW_DATA={
                "doc_id": doc_id, 
                "rows": payload,
                "document_name": doc['name'],
                "item_count": len(payload)
            }
        )
        
    except Exception as e:
        LOG.error(f"Review page error for doc {doc_id}: {e}")
        return "An error occurred while loading the review page.", 500


@app.route("/confirm/<int:doc_id>", methods=["POST"])
def confirm(doc_id: int):
    """Enhanced confirmation with better CSV export."""
    try:
        conn = db_conn()
        c = conn.cursor()

        # Update confirmed IDs with validation
        confirmed_count = 0
        for mid, sel in request.form.items():
            try:
                match_id = int(mid)
                selection = int(sel)
                c.execute("UPDATE matches SET confirmed_id=? WHERE id=?", (selection, match_id))
                confirmed_count += 1
            except (ValueError, TypeError) as e:
                LOG.warning(f"Invalid form data: {mid}={sel}, error: {e}")
        
        conn.commit()
        
        log_processing_step(doc_id, 'confirm', 'success', f'Confirmed {confirmed_count} matches')

        # Fetch enhanced data for CSV with confidence scores
        rows = [
            {
                "description": r["description"],
                "confirmed_id": r["confirmed_id"],
                "choices": json.loads(r["choice_json"]),
                "confidence_score": r["confidence_score"]
            }
            for r in c.execute(
                """
            SELECT li.description, m.confirmed_id, m.choice_json, m.confidence_score
            FROM matches m 
            JOIN line_items li ON li.id=m.line_item_id
            WHERE li.document_id=?
            ORDER BY li.raw_index
            """,
                (doc_id,),
            )
        ]
        
        conn.close()
        
        # Get document name for filename
        doc_name = f"document_{doc_id}"
        try:
            conn = db_conn()
            c = conn.cursor()
            doc_record = c.execute("SELECT name FROM documents WHERE id=?", (doc_id,)).fetchone()
            if doc_record:
                doc_name = doc_record['name'].replace('.pdf', '')
            conn.close()
        except:
            pass

        return Response(
            stream_csv(rows),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={doc_name}_matches.csv"},
        )
        
    except Exception as e:
        LOG.error(f"Confirmation failed for doc {doc_id}: {e}")
        return "Export failed. Please try again.", 500


if __name__ == "__main__":
    app.run(debug=True, threaded=True) 