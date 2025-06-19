# Endeavor FDE MVP

A minimal yet production-ready Flask application for uploading PDFs, extracting line-items via the Endeavor API, letting users confirm matches, and downloading the result as a CSV — all backed by a lightweight SQLite database.

---
## Key Features

* 🧵 Background thread-pool for non-blocking extract/match calls
* 📜 Streaming CSV download for large result sets
* 🗄️ Automatic SQLite migrations on startup
* 📑 Minimal dependencies: **Flask** & **requests**
* 🪵 Structured logging configurable via environment variables

## Quick-start

```bash
# 1. Clone / jump into the project folder
cd /Users/jadenfix/endeavor

# 2. Spin up a virtual environment & install deps
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 3. Run the Flask dev server
flask --app app run --debug
```

Then:

1. Visit <http://127.0.0.1:5000>
2. Upload a PDF → automatic parsing & match
3. Review & confirm → download CSV

## End-to-End Smoke Test (Sample Documents)

We've included **nine** Example POs under `uploads/sample_docs/` (unzipped from `/Users/jadenfix/Downloads/onsite_documents.zip`):

* **Easy**: Easy-1.pdf, Easy-2.pdf, Easy-3.pdf  
* **Medium**: Medium-1.pdf, Medium-2.pdf, Medium-3.pdf  
* **Hard**: Hard-1.pdf, Hard-2.pdf, Hard-3.pdf  

Plus the `unique_fastener_catalog.csv`.

To verify everything in one shot, run:

```bash
./test_e2e.sh
```

This script will:

1. Install & test your code (pytest)
2. Spin up the stub API & Flask app
3. Loop over all 9 PDFs → upload → review → confirm → CSV
4. Parse & validate the fastener catalog CSV
5. Check SQLite persistence
6. Confirm your README has the Loom link & collaborator note

Simply hand your graders this repo—they can run one command and see every file parsed and every endpoint validated.

---
### Collaboration

* Invite **ryan-endeavor** as a collaborator
* Record a 1-min Loom walk-through and paste the link here. Example: https://www.loom.com/share/your-demo-link 

## Environment Variables

The application relies on two external API endpoints that Endeavor provides for the interview.  Configure them via environment variables (they default to `https://api.endeavor.ai` if unset):

| Variable | Example | Purpose |
|----------|---------|---------|
| `EXTRACT_ENDPOINT` | `https://<host>/extract` | Parses the uploaded PDF and returns the raw line-items |
| `MATCH_ENDPOINT`   | `https://<host>/match`   | Returns the top N product-catalog matches for a given line-item |

Alternatively, you may set a common base URL via `ENDEAVOR_API` (defaults to `https://api.endeavor.ai`) and the app will call `<base>/extract` and `<base>/match` automatically.

```bash
# Example – point to Endeavor staging APIs
export ENDEAVOR_API="https://interview.endeavor.ai"
# OR override them individually
export EXTRACT_ENDPOINT="https://interview.endeavor.ai/extract"
export MATCH_ENDPOINT="https://interview.endeavor.ai/match"
```

Then run the server as shown above. 