"""
Lightweight stub of the Endeavor extract & match APIs
"""
from flask import Flask, request, jsonify

app = Flask("stub_api")


@app.route("/extraction_api", methods=["POST"])
def extract():
    """Return dummy extraction results in the production API format."""
    # Production API returns array of objects like:
    # [{"Request Item": "...", "Amount": ..., "Unit Price": null, "Total": null}, ...]
    return jsonify([
        {
            "Request Item": "Easy-1: Widget A",
            "Amount": 100,
            "Unit Price": None,
            "Total": None
        },
        {
            "Request Item": "Easy-1: Widget B", 
            "Amount": 50,
            "Unit Price": None,
            "Total": None
        },
    ])


@app.route("/match", methods=["GET"])
def match():
    """Return dummy catalog matches in production API format."""
    # Production API returns array of objects like:
    # [{"match": "...", "score": ...}, ...]
    query = request.args.get("query", "")
    limit = int(request.args.get("limit", 5))
    
    # Return dummy matches
    matches = [
        {"match": "CAT-1000 – Widget A", "score": 0.95},
        {"match": "CAT-2000 – Widget B", "score": 0.87},
    ]
    
    return jsonify(matches[:limit])


if __name__ == "__main__":
    # Run stub on port 5001 so it won't conflict with the main app
    app.run(port=5001) 