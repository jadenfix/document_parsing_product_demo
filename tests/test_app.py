"""
Enhanced test suite for the Endeavor FDE MVP
Tests cover all aspects including error handling, UI features, and API integration.
"""

import pytest
import json
import tempfile
import os
import sqlite3
from unittest.mock import patch, MagicMock

from app import app, init_db, db_conn, log_processing_step


@pytest.fixture
def client():
    """Create a test client with temporary database."""
    db_fd, app.config['DATABASE'] = tempfile.mkstemp()
    app.config['TESTING'] = True
    
    # Use temporary database
    original_db_path = app.config.get('DB_PATH', 'data.db')
    app.config['DB_PATH'] = app.config['DATABASE']
    
    # Temporarily override the global DB_PATH in the app module
    import app as app_module
    original_module_db_path = app_module.DB_PATH
    app_module.DB_PATH = app.config['DATABASE']
    
    init_db()
    
    with app.test_client() as client:
        with app.app_context():
            yield client
    
    # Cleanup
    os.close(db_fd)
    os.unlink(app.config['DATABASE'])
    app_module.DB_PATH = original_module_db_path


def test_home_page(client):
    """Test the enhanced home page with statistics."""
    rv = client.get('/')
    assert rv.status_code == 200
    assert b'Document Processing Platform' in rv.data
    assert b'Upload' in rv.data
    assert b'progress-steps' in rv.data


def test_api_stats(client):
    """Test the statistics API endpoint."""
    rv = client.get('/api/stats')
    assert rv.status_code == 200
    
    data = json.loads(rv.data)
    assert 'total_documents' in data
    assert 'total_items' in data
    assert 'success_rate' in data
    assert 'avg_processing_time' in data


def test_upload_no_file(client):
    """Test upload without file."""
    rv = client.post('/upload', data={})
    assert rv.status_code == 400
    
    data = json.loads(rv.data)
    assert 'error' in data
    assert 'No file provided' in data['error']


def test_upload_empty_filename(client):
    """Test upload with empty filename."""
    rv = client.post('/upload', data={'file': (None, '')})
    assert rv.status_code == 400
    
    data = json.loads(rv.data)
    assert 'error' in data
    assert 'No file selected' in data['error']


def test_upload_non_pdf(client):
    """Test upload with non-PDF file."""
    rv = client.post('/upload', data={
        'file': (open(__file__, 'rb'), 'test.txt')
    })
    assert rv.status_code == 400
    
    data = json.loads(rv.data)
    assert 'error' in data
    assert 'Only PDF files are supported' in data['error']


@patch('app.make_api_request')
def test_upload_success(mock_api, client):
    """Test successful PDF upload and processing."""
    # Mock successful extraction API response
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"Request Item": "Test Item 1", "Amount": 5, "Unit Price": 10.0, "Total": 50.0},
        {"Request Item": "Test Item 2", "Amount": 3, "Unit Price": 15.0, "Total": 45.0}
    ]
    mock_api.return_value = mock_response
    
    # Create a dummy PDF file for testing
    pdf_content = b'%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n'
    
    with patch('app.SYNC_PARSE', True):
        rv = client.post('/upload', data={
            'file': (io.BytesIO(pdf_content), 'test.pdf')
        }, content_type='multipart/form-data')
    
    assert rv.status_code == 302  # Redirect to review page
    
    # Verify document was created
    conn = db_conn()
    c = conn.cursor()
    doc = c.execute("SELECT * FROM documents WHERE name='test.pdf'").fetchone()
    assert doc is not None
    assert doc['status'] == 'completed'
    assert doc['item_count'] == 2
    conn.close()


def test_review_nonexistent_document(client):
    """Test review page for non-existent document."""
    rv = client.get('/review/999')
    assert rv.status_code == 404
    assert b'Document not found' in rv.data


def test_processing_logs(client):
    """Test processing logging functionality."""
    # Create a test document first
    conn = db_conn()
    c = conn.cursor()
    c.execute("INSERT INTO documents(name, status) VALUES('test.pdf', 'processing')")
    conn.commit()
    doc_id = c.lastrowid
    conn.close()
    
    # Test logging
    log_processing_step(doc_id, 'upload', 'success', 'Test upload', 100)
    
    # Verify log was created
    conn = db_conn()
    c = conn.cursor()
    logs = c.execute("SELECT * FROM processing_logs WHERE document_id=?", (doc_id,)).fetchall()
    assert len(logs) == 1
    assert logs[0]['step'] == 'upload'
    assert logs[0]['status'] == 'success'
    assert logs[0]['message'] == 'Test upload'
    assert logs[0]['duration_ms'] == 100
    conn.close()


@patch('app.make_api_request')
def test_review_with_matching(mock_api, client):
    """Test review page with automatic matching."""
    # Setup test data
    conn = db_conn()
    c = conn.cursor()
    c.execute("INSERT INTO documents(name, status) VALUES('test.pdf', 'completed')")
    doc_id = c.lastrowid
    c.execute("INSERT INTO line_items(document_id, description, raw_index) VALUES(?, 'Test Item', 0)", (doc_id,))
    conn.commit()
    conn.close()
    
    # Mock matching API response
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"match": "Matched Item 1", "score": 95},
        {"match": "Matched Item 2", "score": 85},
        {"match": "Matched Item 3", "score": 75}
    ]
    mock_api.return_value = mock_response
    
    rv = client.get(f'/review/{doc_id}')
    assert rv.status_code == 200
    assert b'Review & Confirm Matches' in rv.data
    assert b'Test Item' in rv.data
    assert b'Matched Item 1' in rv.data


@patch('app.make_api_request')
def test_review_with_api_failure(mock_api, client):
    """Test review page when matching API fails."""
    # Setup test data
    conn = db_conn()
    c = conn.cursor()
    c.execute("INSERT INTO documents(name, status) VALUES('test.pdf', 'completed')")
    doc_id = c.lastrowid
    c.execute("INSERT INTO line_items(document_id, description, raw_index) VALUES(?, 'Test Item', 0)", (doc_id,))
    conn.commit()
    conn.close()
    
    # Mock API failure
    mock_api.side_effect = Exception("API Error")
    
    rv = client.get(f'/review/{doc_id}')
    assert rv.status_code == 200
    assert b'No match found' in rv.data  # Should show fallback match


def test_confirm_with_invalid_data(client):
    """Test confirmation with invalid form data."""
    # Setup test data
    conn = db_conn()
    c = conn.cursor()
    c.execute("INSERT INTO documents(name, status) VALUES('test.pdf', 'completed')")
    doc_id = c.lastrowid
    c.execute("INSERT INTO line_items(document_id, description, raw_index) VALUES(?, 'Test Item', 0)", (doc_id,))
    item_id = c.lastrowid
    c.execute("INSERT INTO matches(line_item_id, choice_json) VALUES(?, ?)", 
              (item_id, json.dumps(["Choice 1", "Choice 2"])))
    match_id = c.lastrowid
    conn.commit()
    conn.close()
    
    # Test with invalid data
    rv = client.post(f'/confirm/{doc_id}', data={
        str(match_id): 'invalid',  # Invalid selection
        'extra_field': '1'  # Extra field that should be ignored
    })
    
    # Should still work but generate CSV with default values
    assert rv.status_code == 200
    assert rv.mimetype == 'text/csv'


def test_confirm_csv_export(client):
    """Test CSV export functionality."""
    # Setup test data
    conn = db_conn()
    c = conn.cursor()
    c.execute("INSERT INTO documents(name, status) VALUES('test.pdf', 'completed')")
    doc_id = c.lastrowid
    c.execute("INSERT INTO line_items(document_id, description, raw_index) VALUES(?, 'Test Item', 0)", (doc_id,))
    item_id = c.lastrowid
    c.execute("INSERT INTO matches(line_item_id, choice_json, confidence_score) VALUES(?, ?, ?)", 
              (item_id, json.dumps(["Choice 1", "Choice 2"]), 0.95))
    match_id = c.lastrowid
    conn.commit()
    conn.close()
    
    rv = client.post(f'/confirm/{doc_id}', data={str(match_id): '0'})
    
    assert rv.status_code == 200
    assert rv.mimetype == 'text/csv'
    assert b'description,confirmed_choice,confidence_score' in rv.data
    assert b'Test Item,Choice 1,0.95' in rv.data


def test_error_document_status(client):
    """Test review page for document with error status."""
    # Setup document with error status
    conn = db_conn()
    c = conn.cursor()
    c.execute("INSERT INTO documents(name, status, error_message) VALUES('error.pdf', 'error', 'Test error')")
    doc_id = c.lastrowid
    conn.commit()
    conn.close()
    
    rv = client.get(f'/review/{doc_id}')
    assert rv.status_code == 500
    assert b'Document processing failed: Test error' in rv.data


def test_database_schema(client):
    """Test that database schema is properly created."""
    conn = db_conn()
    c = conn.cursor()
    
    # Check tables exist
    tables = c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    table_names = [t[0] for t in tables]
    
    assert 'documents' in table_names
    assert 'line_items' in table_names
    assert 'matches' in table_names
    assert 'processing_logs' in table_names
    
    # Check indexes exist
    indexes = c.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
    index_names = [i[0] for i in indexes]
    
    assert 'idx_documents_status' in index_names
    assert 'idx_line_items_doc_id' in index_names
    assert 'idx_matches_line_item_id' in index_names
    
    conn.close()


# Import required for test
import io 