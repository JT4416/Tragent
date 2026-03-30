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
        try:
            return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            # File may be partially truncated; re-seed from scratch
            return self._seed(name)

    def save(self, name: str, data: dict) -> None:
        content = yaml.dump(data, default_flow_style=False, sort_keys=False)
        lines = content.splitlines()
        if len(lines) > self._max_lines:
            content = "\n".join(lines[: self._max_lines])
        self._path(name).write_text(content, encoding="utf-8")

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
                "inverse_etfs": {
                    "note": (
                        "Inverse ETFs allow bearish exposure without short selling. "
                        "Buy these when bearish — no margin, no unlimited downside."
                    ),
                    "universe": [
                        {"symbol": "SH",  "tracks": "S&P 500 inverse 1x",
                         "use_when": "broadly bearish on large caps"},
                        {"symbol": "SDS", "tracks": "S&P 500 inverse 2x",
                         "use_when": "high conviction broad market decline"},
                        {"symbol": "QID", "tracks": "Nasdaq-100 inverse 2x",
                         "use_when": "high conviction tech sector decline"},
                        {"symbol": "DOG", "tracks": "Dow Jones inverse 1x",
                         "use_when": "broadly bearish on industrials/blue chips"},
                    ],
                    "caution": (
                        "2x ETFs decay over time — do not hold for more than 1–2 days. "
                        "1x ETFs (SH, DOG) are suitable for slightly longer holds."
                    ),
                },
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
        }
        data = seeds.get(name, {"overview": {"last_updated": str(date.today())}})
        self.save(name, data)
        return data
