import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Position:
    symbol: str
    direction: str          # "long" only — short selling disabled
    entry_price: float
    stop_loss: float
    trailing_stop: float
    quantity: int
    entry_time: str | None = None   # ISO-8601 UTC string, e.g. "2026-03-30T10:00:00+00:00"


_DEFAULT_DB_DIR = Path(__file__).parent.parent.parent / "state"


class StateStore:
    def __init__(self, agent_id: str, db_dir: Path = _DEFAULT_DB_DIR):
        db_dir.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_dir / f"{agent_id}.db",
                                     check_same_thread=False)
        self._create_tables()
        self._migrate()

    def __del__(self):
        if hasattr(self, '_conn'):
            self._conn.close()

    def _create_tables(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS positions (
                symbol TEXT PRIMARY KEY,
                direction TEXT,
                entry_price REAL,
                stop_loss REAL,
                trailing_stop REAL,
                quantity INTEGER,
                entry_time TEXT
            );
            CREATE TABLE IF NOT EXISTS round_state (
                key TEXT PRIMARY KEY,
                value REAL
            );
        """)
        self._conn.commit()

    def _migrate(self):
        """Add entry_time column to existing databases that predate this field."""
        cols = {row[1] for row in
                self._conn.execute("PRAGMA table_info(positions)").fetchall()}
        if "entry_time" not in cols:
            self._conn.execute(
                "ALTER TABLE positions ADD COLUMN entry_time TEXT")
            self._conn.commit()

    def save_position(self, pos: Position) -> None:
        self._conn.execute("""
            INSERT OR REPLACE INTO positions
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (pos.symbol, pos.direction, pos.entry_price,
              pos.stop_loss, pos.trailing_stop, pos.quantity, pos.entry_time))
        self._conn.commit()

    def get_positions(self) -> list[Position]:
        rows = self._conn.execute("SELECT * FROM positions").fetchall()
        return [Position(*r) for r in rows]

    def get_position(self, symbol: str) -> "Position | None":
        row = self._conn.execute(
            "SELECT * FROM positions WHERE symbol=?", (symbol,)).fetchone()
        return Position(*row) if row else None

    def remove_position(self, symbol: str) -> None:
        self._conn.execute("DELETE FROM positions WHERE symbol=?", (symbol,))
        self._conn.commit()

    def update_round_pnl(self, pnl: float) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO round_state VALUES ('round_pnl', ?)", (pnl,))
        self._conn.commit()

    def get_round_pnl(self) -> float:
        row = self._conn.execute(
            "SELECT value FROM round_state WHERE key='round_pnl'").fetchone()
        return row[0] if row else 0.0
