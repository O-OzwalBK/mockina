"""Write the JSON schema of every public contracts model to docs/schemas/.

Run from the repo root:
    uv run --package contracts python scripts/export_schemas.py

The output folder is generated. Do not edit its files by hand; rerun this script
after changing a model.
"""

import json
from pathlib import Path

from contracts.schemas import all_schemas

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "schemas"


def main() -> None:
    """Replace the contents of the output folder with freshly generated schemas."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for old_file in OUTPUT_DIR.glob("*.json"):
        old_file.unlink()
    for name, schema in all_schemas().items():
        text = json.dumps(schema, indent=2, sort_keys=True) + "\n"
        (OUTPUT_DIR / f"{name}.json").write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote docs/schemas/{name}.json")


if __name__ == "__main__":
    main()