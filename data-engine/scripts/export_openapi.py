from __future__ import annotations

import json
import sys
from pathlib import Path


DATA_ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATA_ENGINE_ROOT))

import main  # noqa: E402


def main_export() -> None:
    target = DATA_ENGINE_ROOT / "openapi.json"
    target.write_text(
        json.dumps(main.app.openapi(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"Wrote {target}")


if __name__ == "__main__":
    main_export()
