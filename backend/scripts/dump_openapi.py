"""Dev only: write the API's OpenAPI document to backend/openapi.json.

The frontend generates its TypeScript types from that file (npm run gen:api), and a
backend test fails when the file is out of date, so the two cannot drift.

Run from backend/:  python -m scripts.dump_openapi
"""

import json
from pathlib import Path

from app.main import app

PATH = Path(__file__).resolve().parent.parent / "openapi.json"


def render() -> str:
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    PATH.write_text(render())
    print(f"wrote {PATH}")
