import pytest
from agents.peer_exchange import PeerExchange


def test_register_and_drain_empty():
    ex = PeerExchange()
    ex.register("agent_a")
    assert ex.drain("agent_a") == []


def test_publish_delivers_to_other_agent():
    ex = PeerExchange()
    ex.register("agent_a")
    ex.register("agent_b")
    insight = {"from_agent": "agent_a", "event": "entry", "symbol": "AAPL"}
    ex.publish("agent_a", insight)
    result = ex.drain("agent_b")
    assert len(result) == 1
    assert result[0]["symbol"] == "AAPL"


def test_publish_does_not_deliver_to_sender():
    ex = PeerExchange()
    ex.register("agent_a")
    ex.register("agent_b")
    ex.publish("agent_a", {"event": "entry"})
    assert ex.drain("agent_a") == []


def test_drain_clears_inbox():
    ex = PeerExchange()
    ex.register("agent_a")
    ex.register("agent_b")
    ex.publish("agent_a", {"event": "entry"})
    ex.drain("agent_b")
    assert ex.drain("agent_b") == []


def test_publish_unregistered_raises():
    ex = PeerExchange()
    ex.register("agent_a")
    with pytest.raises(KeyError):
        ex.publish("agent_z", {"event": "entry"})


def test_drain_unregistered_raises():
    ex = PeerExchange()
    with pytest.raises(KeyError):
        ex.drain("agent_z")


def test_multiple_insights_drained_in_order():
    ex = PeerExchange()
    ex.register("agent_a")
    ex.register("agent_b")
    ex.publish("agent_a", {"event": "entry", "n": 1})
    ex.publish("agent_a", {"event": "close", "n": 2})
    result = ex.drain("agent_b")
    assert len(result) == 2
    assert result[0]["n"] == 1
    assert result[1]["n"] == 2
