#!/usr/bin/env python3
"""
Quick test of custom matching functionality
"""
import os
os.environ['DB_PATH'] = 'test_custom.db'
os.environ['USE_STUB_API'] = '1'

from app import custom_match, PRODUCT_CATALOG

def test_custom_matching():
    print(f"Loaded catalog with {len(PRODUCT_CATALOG)} products")
    
    if len(PRODUCT_CATALOG) == 0:
        print("⚠️  No catalog loaded - creating sample catalog")
        # Create a sample catalog for testing
        import app
        app.PRODUCT_CATALOG = [
            "Brass Nut 1/2\" 20mm Galvanized",
            "Steel Bolt M6 25mm",
            "Aluminum Washer 10mm",
            "Stainless Steel Screw 4x40mm",
            "Copper Pipe Fitting 15mm",
            "Galvanized Steel Rod 8mm",
            "Bronze Bearing 12mm",
            "Titanium Fastener Set"
        ]
    
    # Test queries
    test_queries = [
        "Brass Nut 1/2\" 20mm Galvanized Coarse (Qty: 143)",
        "Steel bolt M6",
        "Aluminum washer",
        "Copper pipe",
        "Unknown product xyz123"
    ]
    
    print("🧪 Testing Custom Matching:")
    for query in test_queries:
        matches = custom_match(query, use_custom=True)
        print(f"\nQuery: {query}")
        if matches:
            for i, match in enumerate(matches[:3]):
                print(f"  {i+1}. {match['name']} (score: {match['score']:.2f})")
        else:
            print("  No matches found")
    
    print("\n✅ Custom matching test completed!")

if __name__ == "__main__":
    test_custom_matching() 