import json
from pathlib import Path

from app.main import app

Path("docs").mkdir(exist_ok=True)
Path("docs/openapi.json").write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8")
