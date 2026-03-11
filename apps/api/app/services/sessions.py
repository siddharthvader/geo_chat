from collections import defaultdict, deque


class SessionMemory:
    def __init__(self, max_turns: int = 6):
        self._store: dict[str, deque[dict[str, str]]] = defaultdict(lambda: deque(maxlen=max_turns))

    def add_turn(self, session_id: str, role: str, content: str) -> None:
        self._store[session_id].append({"role": role, "content": content})

    def get_turns(self, session_id: str) -> list[dict[str, str]]:
        return list(self._store[session_id])


session_memory = SessionMemory()
