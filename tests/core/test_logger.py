import json
from pathlib import Path
from core.logger import get_logger

def test_logs_json_to_file(tmp_dir):
    logger = get_logger("agent_a", "trades", log_dir=tmp_dir)
    logger.log({"trade_id": "t_001", "symbol": "AAPL", "action": "buy"})
    log_files = list((tmp_dir / "agent_a" / "trades").glob("*.json"))
    assert len(log_files) == 1
    entries = json.loads(log_files[0].read_text())
    assert entries[0]["symbol"] == "AAPL"

def test_appends_multiple_entries(tmp_dir):
    logger = get_logger("agent_a", "trades", log_dir=tmp_dir)
    logger.log({"event": "first"})
    logger.log({"event": "second"})
    log_files = list((tmp_dir / "agent_a" / "trades").glob("*.json"))
    entries = json.loads(log_files[0].read_text())
    assert len(entries) == 2
