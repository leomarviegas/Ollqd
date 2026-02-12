"""SQLite persistence for config overrides and user accounts.

Stores runtime config changes so they survive container restarts.
All values are stored as text; callers handle type coercion on load.
Also manages the users table for authentication.
"""

import logging
import sqlite3
import threading

import bcrypt

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

_USERS_SCHEMA = """\
CREATE TABLE IF NOT EXISTS users (
    username      TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'user',
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
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
    """Create the config_overrides and users tables, seed default admin."""
    global _db_path
    _db_path = db_path
    conn = _get_conn()
    conn.execute(_SCHEMA)
    conn.execute(_USERS_SCHEMA)
    conn.commit()
    _seed_default_admin()
    log.info("Config DB initialised at %s", db_path)


def _seed_default_admin() -> None:
    """Insert admin/admin if no users exist yet."""
    conn = _get_conn()
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if count == 0:
        pw_hash = bcrypt.hashpw(b"admin", bcrypt.gensalt()).decode()
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("admin", pw_hash, "admin"),
        )
        conn.commit()
        log.info("Seeded default admin user")


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


# ── User management ──────────────────────────────────────


def verify_user(username: str, password: str) -> dict | None:
    """Check credentials; return {"username", "role", "created_at"} or None."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT password_hash, role, created_at FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    if row is None:
        return None
    pw_hash, role, created_at = row
    if not bcrypt.checkpw(password.encode(), pw_hash.encode()):
        return None
    return {"username": username, "role": role, "created_at": created_at}


def list_users() -> list[dict]:
    """Return all users (without password hashes)."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT username, role, created_at FROM users ORDER BY created_at"
    ).fetchall()
    return [{"username": r[0], "role": r[1], "created_at": r[2]} for r in rows]


def create_user(username: str, password: str, role: str = "user") -> dict | None:
    """Create a user; return user dict or None if username taken."""
    conn = _get_conn()
    existing = conn.execute(
        "SELECT 1 FROM users WHERE username = ?", (username,)
    ).fetchone()
    if existing:
        return None
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    conn.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
        (username, pw_hash, role),
    )
    conn.commit()
    row = conn.execute(
        "SELECT username, role, created_at FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    return {"username": row[0], "role": row[1], "created_at": row[2]}


def delete_user(username: str) -> tuple[bool, str]:
    """Delete a user. Returns (success, error_message).

    Prevents deleting the last admin.
    """
    conn = _get_conn()
    row = conn.execute(
        "SELECT role FROM users WHERE username = ?", (username,)
    ).fetchone()
    if row is None:
        return False, "user not found"
    if row[0] == "admin":
        admin_count = conn.execute(
            "SELECT COUNT(*) FROM users WHERE role = 'admin'"
        ).fetchone()[0]
        if admin_count <= 1:
            return False, "cannot delete last admin"
    conn.execute("DELETE FROM users WHERE username = ?", (username,))
    conn.commit()
    return True, ""
