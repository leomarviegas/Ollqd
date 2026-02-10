"""SQLite persistence for config overrides.

Stores runtime config changes so they survive container restarts.
All values are stored as text; callers handle type coercion on load.
"""

import logging
import sqlite3
import threading

log = logging.getLogger("ollqd.worker.config_db")

_db_path: str | None = None
_local = threading.local()

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS config_overrides (
    section    TEXT NOT NULL,
    key        TEXT NOT NULL,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (section, key)
);
"""


def _get_conn() -> sqlite3.Connection:
    """Return a per-thread reusable connection."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        if _db_path is None:
            raise RuntimeError("config_db not initialised — call init_db() first")
        conn = sqlite3.connect(_db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        _local.conn = conn
    return conn


def init_db(db_path: str) -> None:
    """Create the config_overrides table if it doesn't exist."""
    global _db_path
    _db_path = db_path
    conn = _get_conn()
    conn.execute(_SCHEMA)
    conn.commit()
    log.info("Config DB initialised at %s", db_path)


def save_override(section: str, key: str, value: str) -> None:
    """Upsert a single config override."""
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO config_overrides (section, key, value, updated_at) "
        "VALUES (?, ?, ?, datetime('now'))",
        (section, key, value),
    )
    conn.commit()


def save_overrides(section: str, data: dict[str, str]) -> None:
    """Upsert multiple config overrides in one transaction."""
    conn = _get_conn()
    conn.executemany(
        "INSERT OR REPLACE INTO config_overrides (section, key, value, updated_at) "
        "VALUES (?, ?, ?, datetime('now'))",
        [(section, k, v) for k, v in data.items()],
    )
    conn.commit()


def delete_overrides(section: str = "", keys: list[str] | None = None) -> list[str]:
    """Delete config overrides, returning the keys that were removed.

    Args:
        section: Section to delete from. Empty string = all sections.
        keys: Specific keys to delete. None/empty = entire section.
    """
    conn = _get_conn()
    if not section:
        # Delete everything
        rows = conn.execute("SELECT section || '.' || key FROM config_overrides").fetchall()
        conn.execute("DELETE FROM config_overrides")
    elif keys:
        placeholders = ",".join("?" for _ in keys)
        rows = conn.execute(
            f"SELECT key FROM config_overrides WHERE section = ? AND key IN ({placeholders})",
            [section, *keys],
        ).fetchall()
        conn.execute(
            f"DELETE FROM config_overrides WHERE section = ? AND key IN ({placeholders})",
            [section, *keys],
        )
    else:
        rows = conn.execute(
            "SELECT key FROM config_overrides WHERE section = ?", (section,)
        ).fetchall()
        conn.execute("DELETE FROM config_overrides WHERE section = ?", (section,))
    conn.commit()
    removed = [r[0] for r in rows]
    log.info("Deleted config overrides: section=%r keys=%s", section or "*", removed)
    return removed


def load_overrides() -> dict[str, dict[str, str]]:
    """Load all saved overrides, grouped by section.

    Returns e.g. {"pii": {"enabled": "true", "use_spacy": "false"}, ...}
    """
    conn = _get_conn()
    rows = conn.execute(
        "SELECT section, key, value FROM config_overrides"
    ).fetchall()
    result: dict[str, dict[str, str]] = {}
    for section, key, value in rows:
        result.setdefault(section, {})[key] = value
    return result
