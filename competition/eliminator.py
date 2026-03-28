import shutil
from pathlib import Path
from agents.expertise_manager import ExpertiseManager

_AGENTS_DIR = Path(__file__).parent.parent / "agents"
_ARCHIVE_DIR = _AGENTS_DIR / "archive"


class RoundEliminator:
    def __init__(self, agents_dir: Path = _AGENTS_DIR,
                 archive_dir: Path = _ARCHIVE_DIR):
        self._agents = agents_dir
        self._archive = archive_dir

    def eliminate(self, loser_id: str, winner_id: str, round_num: int) -> None:
        loser_dir = self._agents / loser_id
        archive_dest = self._archive / f"round_{round_num}_{loser_id}"

        # Archive loser's expertise files
        archive_dest.mkdir(parents=True, exist_ok=True)
        for f in loser_dir.glob("*.yaml"):
            shutil.copy2(f, archive_dest / f.name)

        # Seed new agent with winner's expertise (copy winner's files to loser dir)
        winner_dir = self._agents / winner_id
        for f in winner_dir.glob("*.yaml"):
            shutil.copy2(f, loser_dir / f.name)

    def determine_loser(self, pnl_a: float, pnl_b: float) -> str | None:
        """Returns loser agent_id, or None if both profitable and tied."""
        if pnl_a < 0 and pnl_b < 0:
            return "agent_a" if pnl_a < pnl_b else "agent_b"
        if pnl_a < 0:
            return "agent_a"
        if pnl_b < 0:
            return "agent_b"
        if pnl_a == pnl_b:
            return None
        return "agent_a" if pnl_a < pnl_b else "agent_b"
