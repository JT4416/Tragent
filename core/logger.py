import json
from datetime import datetime, timezone
from pathlib import Path


class Logger:
    def __init__(self, agent: str, category: str, log_dir: Path):
        self._dir = log_dir / agent / category
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self) -> Path:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self._dir / f"{date}.json"

    def log(self, entry: dict) -> None:
        entry = {**entry, "_ts": datetime.now(timezone.utc).isoformat()}
        path = self._path()
        existing = json.loads(path.read_text()) if path.exists() else []
        existing.append(entry)
        path.write_text(json.dumps(existing, indent=2))


_ROOT_LOG_DIR = Path(__file__).parent.parent / "logs"


def get_logger(agent: str, category: str, log_dir: Path = _ROOT_LOG_DIR) -> Logger:
    return Logger(agent, category, log_dir)
