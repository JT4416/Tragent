from core.state.persistence import StateStore, Position

def test_save_and_load_position(tmp_dir):
    store = StateStore("agent_a", db_dir=tmp_dir)
    pos = Position(symbol="AAPL", direction="long", entry_price=182.50,
                   stop_loss=178.85, trailing_stop=179.25, quantity=10)
    store.save_position(pos)
    loaded = store.get_positions()
    assert len(loaded) == 1
    assert loaded[0].symbol == "AAPL"
    assert loaded[0].entry_price == 182.50

def test_remove_position(tmp_dir):
    store = StateStore("agent_a", db_dir=tmp_dir)
    pos = Position(symbol="MSFT", direction="long", entry_price=400.0,
                   stop_loss=392.0, trailing_stop=394.0, quantity=5)
    store.save_position(pos)
    store.remove_position("MSFT")
    assert store.get_positions() == []

def test_save_and_load_round_pnl(tmp_dir):
    store = StateStore("agent_a", db_dir=tmp_dir)
    store.update_round_pnl(250.75)
    assert store.get_round_pnl() == 250.75

def test_round_pnl_default_is_zero(tmp_dir):
    store = StateStore("agent_a", db_dir=tmp_dir)
    assert store.get_round_pnl() == 0.0
