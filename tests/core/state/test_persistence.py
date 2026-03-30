import sqlite3
from core.state.persistence import StateStore, Position


def test_save_and_load_position(tmp_path):
    store = StateStore("agent_a", db_dir=tmp_path)
    pos = Position(symbol="AAPL", direction="long", entry_price=182.50,
                   stop_loss=178.85, trailing_stop=179.25, quantity=10,
                   entry_time="2026-03-30T10:00:00+00:00")
    store.save_position(pos)
    loaded = store.get_positions()
    assert len(loaded) == 1
    assert loaded[0].symbol == "AAPL"
    assert loaded[0].entry_price == 182.50
    assert loaded[0].entry_time == "2026-03-30T10:00:00+00:00"


def test_remove_position(tmp_path):
    store = StateStore("agent_a", db_dir=tmp_path)
    pos = Position(symbol="MSFT", direction="long", entry_price=400.0,
                   stop_loss=392.0, trailing_stop=394.0, quantity=5,
                   entry_time="2026-03-30T10:00:00+00:00")
    store.save_position(pos)
    store.remove_position("MSFT")
    assert store.get_positions() == []


def test_save_and_load_round_pnl(tmp_path):
    store = StateStore("agent_a", db_dir=tmp_path)
    store.update_round_pnl(250.75)
    assert store.get_round_pnl() == 250.75


def test_round_pnl_default_is_zero(tmp_path):
    store = StateStore("agent_a", db_dir=tmp_path)
    assert store.get_round_pnl() == 0.0


def test_get_position_returns_none_when_missing(tmp_path):
    store = StateStore("agent_a", db_dir=tmp_path)
    assert store.get_position("AAPL") is None


def test_get_position_returns_position(tmp_path):
    store = StateStore("agent_a", db_dir=tmp_path)
    pos = Position(symbol="NVDA", direction="long", entry_price=800.0,
                   stop_loss=784.0, trailing_stop=788.0, quantity=3,
                   entry_time="2026-03-30T11:00:00+00:00")
    store.save_position(pos)
    loaded = store.get_position("NVDA")
    assert loaded is not None
    assert loaded.symbol == "NVDA"
    assert loaded.direction == "long"
    assert loaded.entry_price == 800.0
    assert loaded.stop_loss == 784.0
    assert loaded.trailing_stop == 788.0
    assert loaded.quantity == 3
    assert loaded.entry_time == "2026-03-30T11:00:00+00:00"


def test_schema_migration_adds_entry_time_to_existing_db(tmp_path):
    """Simulate a DB that was created before entry_time existed."""
    db_path = tmp_path / "agent_a.db"
    # Create old schema without entry_time
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE positions (
            symbol TEXT PRIMARY KEY,
            direction TEXT,
            entry_price REAL,
            stop_loss REAL,
            trailing_stop REAL,
            quantity INTEGER
        );
    """)
    conn.execute(
        "INSERT INTO positions VALUES (?, ?, ?, ?, ?, ?)",
        ("SPY", "long", 500.0, 490.0, 495.0, 5),
    )
    conn.commit()
    conn.close()

    # Opening StateStore should migrate without error
    store = StateStore("agent_a", db_dir=tmp_path)
    positions = store.get_positions()
    assert len(positions) == 1
    assert positions[0].symbol == "SPY"
    assert positions[0].entry_time is None  # migrated rows have NULL
