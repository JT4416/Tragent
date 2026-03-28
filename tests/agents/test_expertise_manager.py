import yaml
from agents.expertise_manager import ExpertiseManager

def test_load_expertise(tmp_dir):
    # seed a file
    data = {"overview": {"last_updated": "2026-03-21", "total_patterns_tracked": 0},
            "breakout_patterns": []}
    (tmp_dir / "market_expertise.yaml").write_text(yaml.dump(data))
    mgr = ExpertiseManager("agent_a", expertise_dir=tmp_dir)
    loaded = mgr.load("market")
    assert loaded["overview"]["total_patterns_tracked"] == 0

def test_save_expertise(tmp_dir):
    mgr = ExpertiseManager("agent_a", expertise_dir=tmp_dir)
    data = {"overview": {"last_updated": "2026-03-21"}, "breakout_patterns": []}
    mgr.save("market", data)
    saved = yaml.safe_load((tmp_dir / "market_expertise.yaml").read_text())
    assert saved["overview"]["last_updated"] == "2026-03-21"

def test_enforces_line_limit(tmp_dir):
    import yaml as _yaml
    mgr = ExpertiseManager("agent_a", expertise_dir=tmp_dir, max_lines=10)
    # Build data that serializes to many lines, then save
    big_data = {"overview": {"last_updated": "2026-03-21"},
                "breakout_patterns": [{"id": str(i), "confidence": 0.5}
                                       for i in range(50)]}
    mgr.save("market", big_data)
    content = (tmp_dir / "market_expertise.yaml").read_text()
    assert len(content.splitlines()) <= 10
