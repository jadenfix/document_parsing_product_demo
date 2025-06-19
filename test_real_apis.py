#!/usr/bin/env python3
"""
Test script to verify integration with real APIs using actual PDF files
"""
import os
import sqlite3
import tempfile
import shutil
from pathlib import Path

# Set up environment to use real APIs
os.environ["EXTRACT_ENDPOINT"] = "https://plankton-app-qajlk.ondigitalocean.app/extraction_api"
os.environ["MATCH_ENDPOINT"] = "https://endeavor-interview-api-gzwki.ondigitalocean.app/match"
os.environ["SYNC_PARSE"] = "1"
os.environ["DB_PATH"] = "real_test.db"

# Import app after setting environment
import importlib.util
spec = importlib.util.spec_from_file_location("app", "app.py")
app_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_module)

def test_real_extraction_and_matching():
    """Test with a real PDF file through the actual APIs"""
    
    # Initialize database
    app_module.init_db()
    
    # Copy a test PDF to uploads
    test_pdf = Path("uploads") / "Easy - 1.pdf"
    if not test_pdf.exists():
        print(f"PDF file not found: {test_pdf}")
        return False
    
    print(f"Testing with PDF: {test_pdf}")
    
    # Test extraction
    try:
        print("Testing extraction...")
        app_module.parse_and_store(1, "Easy - 1.pdf")
        print("✓ Extraction successful")
    except Exception as e:
        print(f"✗ Extraction failed: {e}")
        return False
    
    # Check database for extracted items
    conn = sqlite3.connect(os.environ["DB_PATH"])
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    items = c.execute("SELECT * FROM line_items WHERE document_id=1").fetchall()
    print(f"✓ Extracted {len(items)} line items:")
    for item in items:
        print(f"  - {item['description']}")
    
    # Test matching by manually triggering it (simulating the review route)
    print("\nTesting matching...")
    for item in items:
        try:
            import requests
            import json
            resp = requests.get(
                app_module.MATCH_ENDPOINT,
                params={"query": item["description"], "limit": 5}
            )
            resp.raise_for_status()
            matches = resp.json()
            choices = [match["match"] for match in matches]
            
            c.execute(
                "INSERT INTO matches(line_item_id, choice_json) VALUES(?,?)",
                (item["id"], json.dumps(choices)),
            )
            print(f"✓ Found {len(choices)} matches for: {item['description'][:50]}...")
            
        except Exception as e:
            print(f"✗ Matching failed for {item['description']}: {e}")
            return False
    
    conn.commit()
    conn.close()
    
    print("\n✓ All tests passed! Real APIs are working correctly.")
    return True

if __name__ == "__main__":
    success = test_real_extraction_and_matching()
    exit(0 if success else 1) 