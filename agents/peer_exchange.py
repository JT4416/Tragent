import queue


class PeerExchange:
    """Thread-safe in-memory exchange for sharing trade insights between agents.

    Register each agent before use. publish() puts an insight into every
    registered inbox except the sender's. drain() returns and clears all
    pending insights for the caller.
    """

    def __init__(self):
        self._inboxes: dict[str, queue.Queue] = {}

    def register(self, agent_id: str) -> None:
        """Create an inbox for agent_id. Call once per agent before threads start."""
        self._inboxes[agent_id] = queue.Queue()

    def publish(self, from_agent_id: str, insight: dict) -> None:
        """Broadcast insight to all agents except the sender."""
        if from_agent_id not in self._inboxes:
            raise KeyError(f"Agent '{from_agent_id}' not registered")
        for agent_id, inbox in self._inboxes.items():
            if agent_id != from_agent_id:
                inbox.put(insight)

    def drain(self, for_agent_id: str) -> list[dict]:
        """Return and clear all pending insights for for_agent_id."""
        if for_agent_id not in self._inboxes:
            raise KeyError(f"Agent '{for_agent_id}' not registered")
        inbox = self._inboxes[for_agent_id]
        items = []
        while True:
            try:
                items.append(inbox.get_nowait())
            except queue.Empty:
                break
        return items
