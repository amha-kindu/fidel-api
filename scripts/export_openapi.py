"""
    Generate a static OpenAPI JSON file for the frontend or CI.

    Usage:
        python scripts/export_openapi.py
"""
import json
from pathlib import Path

from app.main import app


def main() -> None:
    openapi = app.openapi()
    output_path = Path("openapi.json")
    output_path.write_text(json.dumps(openapi, indent=2))
    print(f"Wrote {output_path.resolve()}")


if __name__ == "__main__":
    main()
