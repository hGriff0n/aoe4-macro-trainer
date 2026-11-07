
import json
from pathlib import Path
from typing import Any, Dict


def read_json(json_file: Path) -> Dict[str, Any]:
    with json_file.open("r", encoding="utf-8") as f:
        return json.load(f)

def parse_json(data) -> dict | None:
    try:
        return json.loads(data)
    except json.JSONDecodeError as exc:
        print(f"Error parsing json: {exc!r}")
        return None