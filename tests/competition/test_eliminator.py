import shutil
import yaml
from competition.eliminator import RoundEliminator
from agents.expertise_manager import ExpertiseManager


def test_archives_loser_and_seeds_winner(tmp_dir):
    # Seed both agents
    winner_dir = tmp_dir / "agent_a"
    loser_dir = tmp_dir / "agent_b"
    archive_dir = tmp_dir / "archive"

    winner_mgr = ExpertiseManager("agent_a", expertise_dir=winner_dir)
    loser_mgr = ExpertiseManager("agent_b", expertise_dir=loser_dir)
    winner_mgr.load("market")
    loser_mgr.load("market")

    # Mark winner's market file as distinct
    winner_data = winner_mgr.load("market")
    winner_data["overview"]["total_patterns_tracked"] = 99
    winner_mgr.save("market", winner_data)

    eliminator = RoundEliminator(agents_dir=tmp_dir, archive_dir=archive_dir)
    eliminator.eliminate(loser_id="agent_b", winner_id="agent_a", round_num=1)

    # Archive should exist
    assert (archive_dir / "round_1_agent_b").exists()

    # New agent_b should have winner's market expertise
    new_mgr = ExpertiseManager("agent_b", expertise_dir=loser_dir)
    new_data = new_mgr.load("market")
    assert new_data["overview"]["total_patterns_tracked"] == 99
