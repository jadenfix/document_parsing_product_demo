"""
Lightweight stub of the Endeavor extract & match APIs
"""
from flask import Flask, request, jsonify

app = Flask("stub_api")


@app.route("/extraction_api", methods=["POST"])
def extract():
    """Return dummy line items in the format that matches the real API."""
    return jsonify([
        {"Request Item": "Easy-1: Widget A", "Amount": 100, "Unit Price": None, "Total": None},
        {"Request Item": "Easy-1: Widget B", "Amount": 200, "Unit Price": None, "Total": None},
    ])


@app.route("/match", methods=["GET"])
def match():
    """Return dummy catalog choices in the format that matches the real API."""
    query = request.args.get('query', '')
    limit = int(request.args.get('limit', 5))
    
    return jsonify([
        {"match": f"CAT-1000 – {query[:20]}...", "score": 95.5},
        {"match": f"CAT-2000 – {query[:20]}...", "score": 87.2},
    ][:limit])


if __name__ == "__main__":
    # Run stub on port 5001 so it won't conflict with the main app
    app.run(port=5001) 