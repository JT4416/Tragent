import json
import subprocess
from datetime import date
from pathlib import Path
from competition.scorer import CompetitionScorer

_LOG_DIR = Path(__file__).parent.parent / "logs" / "competition"


class DailyReporter:
    def __init__(self, scorer_a: CompetitionScorer,
                 scorer_b: CompetitionScorer,
                 log_dir: Path = _LOG_DIR):
        self._a = scorer_a
        self._b = scorer_b
        self._dir = log_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def generate(self) -> dict:
        stats_a = self._a.stats()
        stats_b = self._b.stats()
        leader = ("agent_a" if stats_a["total_pnl"] > stats_b["total_pnl"]
                  else "agent_b" if stats_b["total_pnl"] > stats_a["total_pnl"]
                  else "tied")
        report = {
            "date": str(date.today()),
            "agent_a": stats_a,
            "agent_b": stats_b,
            "leader": leader,
            "divergence_notes": "",
        }
        path = self._dir / f"{date.today()}.json"
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report

    def auto_commit(self) -> None:
        root = Path(__file__).parent.parent
        subprocess.run(["git", "-C", str(root), "add",
                        "logs/", "agents/agent_a/", "agents/agent_b/"],
                       check=False)
        subprocess.run(["git", "-C", str(root), "commit", "-m",
                        f"chore: daily auto-commit {date.today()}"],
                       check=False)
        subprocess.run(["git", "-C", str(root), "push"], check=False)
