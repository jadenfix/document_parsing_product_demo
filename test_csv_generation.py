#!/usr/bin/env python3
"""
Test script to verify CSV generation functionality
"""
import os
import requests
import tempfile

# Set environment variables for testing
os.environ['DB_PATH'] = 'test_csv.db'
os.environ['SYNC_PARSE'] = '1'
os.environ['USE_STUB_API'] = '1'

import app

def test_csv_generation():
    """Test that CSV generation works correctly"""
    print("Testing CSV generation...")
    
    # Create test data structure that matches what the confirm endpoint expects
    test_rows = [
        {
            "description": "Brass Nut 1/2\" 20mm Galvanized Coarse (Qty: 143)",
            "confirmed_id": 0,
            "choices": [
                {"name": "Brass Nut 1/2\" 20mm Galvanized", "score": 0.95},
                {"name": "Steel Nut 1/2\" 20mm", "score": 0.85}
            ]
        },
        {
            "description": "Stainless Steel Stud M6 10mm Galvanized Wood (Qty: 364)",
            "confirmed_id": 1,
            "choices": [
                {"name": "Stainless Steel Stud M6 10mm", "score": 0.92},
                {"name": "Steel Stud M6 10mm Galvanized", "score": 0.88}
            ]
        }
    ]
    
    # Test CSV generation
    csv_lines = list(app.stream_csv(test_rows))
    
    print("Generated CSV:")
    for line in csv_lines:
        print(line.strip())
    
    # Verify CSV structure
    assert csv_lines[0] == "description,confirmed_choice\n"
    # Quotes are properly escaped as "" in CSV format
    assert 'Brass Nut 1/2"" 20mm Galvanized Coarse' in csv_lines[1]
    assert 'Brass Nut 1/2"" 20mm Galvanized' in csv_lines[1]
    assert "Stainless Steel Stud M6 10mm Galvanized Wood" in csv_lines[2]
    assert "Steel Stud M6 10mm Galvanized" in csv_lines[2]
    
    print("✅ CSV generation test passed!")

if __name__ == "__main__":
    test_csv_generation() 