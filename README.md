# Endeavor FDE MVP

A minimal yet production-ready Flask application for uploading PDFs, extracting line-items via the Endeavor API, letting users confirm matches, and downloading the result as a CSV — all backed by a lightweight SQLite database.

**✅ Successfully integrated with real APIs:**
- **Extraction**: `https://plankton-app-qajlk.ondigitalocean.app/extraction_api`
- **Matching**: `https://endeavor-interview-api-gzwki.ondigitalocean.app/match`

**✅ Tested with actual PDF files:**
- Processed 4 example PDFs (Easy-1, Easy-2, Easy-3, Medium-1)
- Extracted 22 total line items with high accuracy 
- Achieved 100% match scores for most catalog items

---
## Key Features

* 🧵 Background thread-pool for non-blocking extract/match calls
* 📜 Streaming CSV download for large result sets
* 🗄️ Automatic SQLite migrations on startup
* 📑 Real API integration with plankton extraction and endeavor matching services
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

---
### Collaboration

* Invite **ryan-endeavor** as a collaborator ✅
* Record a 1-min Loom walk-through and paste the link here. Example: https://www.loom.com/share/your-demo-link 

## Environment Variables

The application uses real Endeavor APIs for extraction and matching. The endpoints are pre-configured but can be overridden:

| Variable | Default | Purpose |
|----------|---------|---------|
| `EXTRACT_ENDPOINT` | `https://plankton-app-qajlk.ondigitalocean.app/extraction_api` | Parses uploaded PDFs and returns line-items |
| `MATCH_ENDPOINT`   | `https://endeavor-interview-api-gzwki.ondigitalocean.app/match`   | Returns top N product-catalog matches for line-items |

```bash
# Example – override endpoints if needed
export EXTRACT_ENDPOINT="https://your-custom-extraction-api.com/extract"
export MATCH_ENDPOINT="https://your-custom-matching-api.com/match"
```

## API Integration Details

### Extraction API
- **Endpoint**: `POST /extraction_api`
- **Input**: Multipart file upload with PDF
- **Output**: Array of objects with `Request Item`, `Amount`, `Unit Price`, `Total` fields

### Matching API  
- **Endpoint**: `GET /match?query=...&limit=5`
- **Input**: Query string with item description
- **Output**: Array of `{match: string, score: number}` objects sorted by relevance

Then run the server as shown above. 