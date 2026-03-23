import yaml
from pathlib import Path
from datetime import date

_DEFAULT_MAX_LINES = 1000
_AGENTS_DIR = Path(__file__).parent


class ExpertiseManager:
    def __init__(self, agent_id: str,
                 expertise_dir: Path | None = None,
                 max_lines: int = _DEFAULT_MAX_LINES):
        self._dir = expertise_dir or (_AGENTS_DIR / agent_id)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._max_lines = max_lines

    def _path(self, name: str) -> Path:
        return self._dir / f"{name}_expertise.yaml"

    def load(self, name: str) -> dict:
        path = self._path(name)
        if not path.exists():
            return self._seed(name)
        return yaml.safe_load(path.read_text()) or {}

    def save(self, name: str, data: dict) -> None:
        content = yaml.dump(data, default_flow_style=False, sort_keys=False)
        lines = content.splitlines()
        if len(lines) > self._max_lines:
            content = "\n".join(lines[: self._max_lines])
        self._path(name).write_text(content)

    def load_all(self) -> dict[str, dict]:
        return {name: self.load(name)
                for name in ("market", "news", "institutional", "trade")}

    def _seed(self, name: str) -> dict:
        seeds = {
            "market": {
                "overview": {"last_updated": str(date.today()),
                             "total_patterns_tracked": 0},
                "breakout_patterns": [],
                "volume_signals": [],
                "known_false_signals": [],
            },
            "news": {
                "overview": {"last_updated": str(date.today())},
                "catalysts": [],
                "ignored_sources": [],
            },
            "institutional": {
                "overview": {"last_updated": str(date.today()),
                             "note": "FINRA dark pool data is weekly — historical only"},
                "institutional_signals": [],
                "dark_pool_patterns": [],
            },
            "trade": {
                "overview": {"last_updated": str(date.today()),
                             "total_trades": 0, "win_rate": 0.0,
                             "avg_gain_pct": 0.0, "avg_loss_pct": 0.0},
                "evolved_parameters": {
                    "stop_loss_pct": 2.0,
                    "trailing_stop_pct": 1.5,
                    "max_position_size_pct": 5.0,
                    "confidence_threshold": 0.65,
                },
                "lessons_learned": [],
                "recent_trades": [],
            },
            "crypto": {
                "overview": {"last_updated": str(date.today()),
                             "activated": False,
                             "preferred_crypto": None,
                             "total_allocated_usd": 0.0},
                "crypto_patterns": [],
                "trade_history": [],
            },
        }
        data = seeds.get(name, {"overview": {"last_updated": str(date.today())}})
        self.save(name, data)
        return data
