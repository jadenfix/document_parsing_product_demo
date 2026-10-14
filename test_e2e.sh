#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
# Uses the active Python environment. All database/uploads are temporary; the
# local fixture provider proves HTTP lifecycle handling, not PDF extraction quality.
exec "${PYTHON:-python3}" tests/http_smoke.py
