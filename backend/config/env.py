import os
from pathlib import Path


def load_dotenv(path: Path) -> None:
    """Dev convenience: fill unset variables from the repo's .env so `uv run pytest` and
    `manage.py` work without `make`. Real environments set variables and ship no .env."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))
