#!/usr/bin/env python3
"""
Comprehensive test script for all PDF files with real APIs
"""
import os
import sqlite3
import json
from pathlib import Path
from datetime import datetime

# Set up environment to use real APIs  
os.environ["EXTRACT_ENDPOINT"] = "https://plankton-app-qajlk.ondigitalocean.app/extraction_api"
os.environ["MATCH_ENDPOINT"] = "https://endeavor-interview-api-gzwki.ondigitalocean.app/match"
os.environ["SYNC_PARSE"] = "1"
os.environ["DB_PATH"] = "comprehensive_test.db"

# Import app after setting environment
import importlib.util
spec = importlib.util.spec_from_file_location("app", "app.py")
app_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_module)

def test_all_pdfs():
    """Test extraction and matching for all available PDF files"""
    
    # Initialize database
    if Path(os.environ["DB_PATH"]).exists():
        Path(os.environ["DB_PATH"]).unlink()
    app_module.init_db()
    
    uploads_dir = Path("uploads")
    pdf_files = list(uploads_dir.glob("*.pdf"))
    pdf_files = [f for f in pdf_files if f.name != "Easy-1.pdf"]  # Skip the tiny test file
    
    print(f"Found {len(pdf_files)} PDF files to test:")
    for pdf in pdf_files:
        print(f"  - {pdf.name}")
    
    conn = sqlite3.connect(os.environ["DB_PATH"])
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    results = {}
    doc_id = 1
    
    for pdf_file in pdf_files:
        print(f"\n{'='*60}")
        print(f"Testing: {pdf_file.name}")
        print(f"{'='*60}")
        
        try:
            # Insert document record
            c.execute("INSERT INTO documents(name) VALUES(?)", (pdf_file.name,))
            conn.commit()
            
            # Test extraction
            print("📄 Extracting line items...")
            app_module.parse_and_store(doc_id, pdf_file.name)
            
            # Get extracted items
            items = c.execute("SELECT * FROM line_items WHERE document_id=?", (doc_id,)).fetchall()
            print(f"✓ Extracted {len(items)} line items")
            
            # Test matching for each item
            print("🔍 Testing matching...")
            for item in items:
                import requests
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
                
                # Show best match for first few items
                if item["raw_index"] < 3:
                    best_match = matches[0] if matches else {"match": "No matches", "score": 0}
                    print(f"  📌 '{item['description'][:40]}...' -> '{best_match['match'][:40]}...' ({best_match['score']:.1f}%)")
            
            conn.commit()
            
            results[pdf_file.name] = {
                "status": "success",
                "items_extracted": len(items),
                "doc_id": doc_id
            }
            
            print(f"✓ {pdf_file.name}: {len(items)} items extracted and matched")
            
        except Exception as e:
            print(f"✗ {pdf_file.name}: {e}")
            results[pdf_file.name] = {
                "status": "error", 
                "error": str(e),
                "doc_id": doc_id
            }
        
        doc_id += 1
    
    conn.close()
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    
    successful = [r for r in results.values() if r["status"] == "success"]
    failed = [r for r in results.values() if r["status"] == "error"]
    
    print(f"✓ Successful: {len(successful)}")
    print(f"✗ Failed: {len(failed)}")
    
    if successful:
        total_items = sum(r["items_extracted"] for r in successful)
        print(f"📊 Total items extracted: {total_items}")
        avg_items = total_items / len(successful)
        print(f"📈 Average items per PDF: {avg_items:.1f}")
    
    if failed:
        print("\nFailed files:")
        for pdf_name, result in results.items():
            if result["status"] == "error":
                print(f"  - {pdf_name}: {result['error']}")
    
    return len(failed) == 0

if __name__ == "__main__":
    print(f"🚀 Starting comprehensive PDF test at {datetime.now()}")
    success = test_all_pdfs()
    print(f"\n🏁 Test completed. {'All tests passed!' if success else 'Some tests failed.'}")
    exit(0 if success else 1) 