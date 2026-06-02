import sqlite3
import bcrypt
from pathlib import Path
from contextlib import contextmanager
from enum import Enum
from typing import Dict, List, Optional

DB_PATH = Path(__file__).parent / "app.db"


class Role(str, Enum):
    ADMIN = "ADMIN"
    CREATOR = "CREATOR"
    VIEWER = "VIEWER"


class SessionStatus(str, Enum):
    DRAFT = "DRAFT"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT    NOT NULL UNIQUE,
                password_hash TEXT    NOT NULL,
                role          TEXT    NOT NULL CHECK(role IN ('ADMIN', 'CREATOR', 'VIEWER')),
                created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT    NOT NULL,
                project_desc TEXT,
                created_by   INTEGER NOT NULL REFERENCES users(id),
                status       TEXT    NOT NULL DEFAULT 'DRAFT'
                                 CHECK(status IN ('DRAFT', 'IN_PROGRESS', 'COMPLETED')),
                created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
                updated_at   TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS step_responses (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                step_number INTEGER NOT NULL,
                prompt_used TEXT    NOT NULL,
                ai_response TEXT,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                UNIQUE(session_id, step_number)
            );

            CREATE TABLE IF NOT EXISTS chat_history (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                step_response_id INTEGER NOT NULL REFERENCES step_responses(id) ON DELETE CASCADE,
                role             TEXT    NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
                content          TEXT    NOT NULL,
                created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
            );
        """)
        _create_default_admin(conn)


def _create_default_admin(conn: sqlite3.Connection) -> None:
    existing = conn.execute(
        "SELECT id FROM users WHERE username = ?", ("admin",)
    ).fetchone()
    if existing:
        return
    password_hash = bcrypt.hashpw(b"admin", bcrypt.gensalt()).decode()
    conn.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
        ("admin", password_hash, Role.ADMIN),
    )


# ---------------------------------------------------------------------------
# User helpers
# ---------------------------------------------------------------------------

def create_user(username: str, password: str, role: Role = Role.VIEWER) -> int:
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, password_hash, role),
        )
        return cur.lastrowid


def verify_user(username: str, password: str) -> Optional[Dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, role FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if row and bcrypt.checkpw(password.encode(), row["password_hash"].encode()):
        return {"id": row["id"], "username": row["username"], "role": row["role"]}
    return None


def get_all_users() -> List[Dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, username, role, created_at FROM users ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]


def update_user_role(user_id: int, role: Role) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))


def delete_user(user_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def create_session(project_name: str, project_desc: str, created_by: int) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO sessions (project_name, project_desc, created_by) VALUES (?, ?, ?)",
            (project_name, project_desc, created_by),
        )
        return cur.lastrowid


def get_sessions(created_by: Optional[int] = None) -> List[Dict]:
    query = "SELECT * FROM sessions"
    params: tuple = ()
    if created_by is not None:
        query += " WHERE created_by = ?"
        params = (created_by,)
    query += " ORDER BY created_at DESC"
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def get_session(session_id: int) -> Optional[Dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
    return dict(row) if row else None


def update_session_status(session_id: int, status: SessionStatus) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE sessions SET status = ?, updated_at = datetime('now') WHERE id = ?",
            (status, session_id),
        )


# ---------------------------------------------------------------------------
# Step response helpers
# ---------------------------------------------------------------------------

def upsert_step_response(
    session_id: int, step_number: int, prompt_used: str, ai_response: str
) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO step_responses (session_id, step_number, prompt_used, ai_response)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(session_id, step_number)
            DO UPDATE SET prompt_used = excluded.prompt_used,
                          ai_response = excluded.ai_response
            """,
            (session_id, step_number, prompt_used, ai_response),
        )
        if cur.lastrowid:
            return cur.lastrowid
        row = conn.execute(
            "SELECT id FROM step_responses WHERE session_id = ? AND step_number = ?",
            (session_id, step_number),
        ).fetchone()
        return row["id"]


def get_step_responses(session_id: int) -> List[Dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM step_responses WHERE session_id = ? ORDER BY step_number",
            (session_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_step_response(step_response_id: int) -> Optional[Dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM step_responses WHERE id = ?", (step_response_id,)
        ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Chat history helpers
# ---------------------------------------------------------------------------

def add_chat_message(step_response_id: int, role: str, content: str) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO chat_history (step_response_id, role, content) VALUES (?, ?, ?)",
            (step_response_id, role, content),
        )
        return cur.lastrowid


def get_chat_history(step_response_id: int) -> List[Dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM chat_history WHERE step_response_id = ? ORDER BY id",
            (step_response_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def clear_chat_history(step_response_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM chat_history WHERE step_response_id = ?", (step_response_id,)
        )


# ---------------------------------------------------------------------------
# Dashboard helpers
# ---------------------------------------------------------------------------

def get_dashboard_kpis() -> Dict:
    """Return KPI counts for the home dashboard."""
    with get_connection() as conn:
        in_progress = conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE status != 'COMPLETED'"
        ).fetchone()[0]
        completed = conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE status = 'COMPLETED'"
        ).fetchone()[0]
        risks = conn.execute(
            "SELECT COUNT(*) FROM step_responses WHERE step_number = 3"
        ).fetchone()[0]
        requirements = conn.execute(
            "SELECT COUNT(*) FROM step_responses WHERE step_number = 4"
        ).fetchone()[0]
    return {
        "in_progress": in_progress,
        "completed": completed,
        "risks": risks,
        "requirements": requirements,
    }


def get_recent_sessions_with_progress(limit: int = 8) -> List[Dict]:
    """Return recent sessions enriched with current step and steps_done count."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT s.id, s.project_name, s.status, s.updated_at,
                   COALESCE(MAX(sr.step_number), 0) AS current_step,
                   COUNT(sr.id) AS steps_done
            FROM sessions s
            LEFT JOIN step_responses sr ON sr.session_id = s.id
            GROUP BY s.id
            ORDER BY s.updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH}")
    print("Default user created: admin / admin")
