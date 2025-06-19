"""
Lightweight stub of the Endeavor extract & match APIs
"""
from flask import Flask, request, jsonify

app = Flask("stub_api")


@app.route("/extract", methods=["POST"])
def extract():
    """Return two dummy line items regardless of input."""
    return jsonify(items=[
        {"description": "Easy-1: Widget A"},
        {"description": "Easy-1: Widget B"},
    ])


@app.route("/match", methods=["POST"])
def match():
    """Return two dummy catalog choices regardless of input."""
    return jsonify(choices=[
        "CAT-1000 – Widget A",
        "CAT-2000 – Widget B",
    ])


if __name__ == "__main__":
    # Run stub on port 5001 so it won't conflict with the main app
    app.run(port=5001) 