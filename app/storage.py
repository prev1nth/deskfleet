import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.environ.get("DB_PATH", "deskfleet.db")


def get_conn() -> sqlite3.Connection:
    _dir = os.path.dirname(DB_PATH)
    if _dir:
        os.makedirs(_dir, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            body TEXT NOT NULL,
            category TEXT,
            decision TEXT,
            reply TEXT,
            escalation_reason TEXT,
            tool_calls TEXT,
            trace_url TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS tool_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER,
            tool_name TEXT,
            arguments TEXT,
            result TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (ticket_id) REFERENCES tickets(id)
        );
        CREATE TABLE IF NOT EXISTS traces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER,
            step_type TEXT,
            step_name TEXT,
            request TEXT,
            response TEXT,
            metadata TEXT,
            duration_ms REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (ticket_id) REFERENCES tickets(id)
        );
        CREATE TABLE IF NOT EXISTS metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            metric_name TEXT NOT NULL,
            labels TEXT,
            value REAL DEFAULT 0,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(metric_name, labels)
        );
    """)
    conn.commit()
    conn.close()


def save_ticket(
    body: str,
    category: str,
    decision: str,
    reply: str,
    escalation_reason: str,
    tool_calls: list[dict],
    trace_url: str | None = None,
) -> int:
    conn = get_conn()
    cursor = conn.execute(
        """INSERT INTO tickets (body, category, decision, reply, escalation_reason, tool_calls, trace_url)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (body, category, decision, reply, escalation_reason, json.dumps(tool_calls), trace_url),
    )
    ticket_id = cursor.lastrowid

    for tc in tool_calls:
        conn.execute(
            """INSERT INTO tool_calls (ticket_id, tool_name, arguments, result)
               VALUES (?, ?, ?, ?)""",
            (ticket_id, tc.get("tool"), json.dumps(tc.get("args", {})), json.dumps(tc.get("result", {}))),
        )

    conn.commit()
    conn.close()
    return ticket_id


def save_trace(
    ticket_id: int,
    step_type: str,
    step_name: str,
    request: dict,
    response: dict,
    metadata: dict | None = None,
    duration_ms: float | None = None,
) -> int:
    conn = get_conn()
    cursor = conn.execute(
        """INSERT INTO traces (ticket_id, step_type, step_name, request, response, metadata, duration_ms)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            ticket_id,
            step_type,
            step_name,
            json.dumps(request),
            json.dumps(response),
            json.dumps(metadata) if metadata else None,
            duration_ms,
        ),
    )
    trace_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return trace_id


def get_ticket(ticket_id: int) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def get_tickets(limit: int = 50, offset: int = 0) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM tickets ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_ticket_traces(ticket_id: int) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM traces WHERE ticket_id = ? ORDER BY created_at ASC",
        (ticket_id,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_ticket_tool_calls(ticket_id: int) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM tool_calls WHERE ticket_id = ? ORDER BY created_at ASC",
        (ticket_id,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_stats() -> dict:
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
    by_decision = conn.execute(
        "SELECT decision, COUNT(*) as count FROM tickets GROUP BY decision"
    ).fetchall()
    by_category = conn.execute(
        "SELECT category, COUNT(*) as count FROM tickets GROUP BY category"
    ).fetchall()
    tool_calls = conn.execute(
        "SELECT tool_name, COUNT(*) as count FROM tool_calls GROUP BY tool_name"
    ).fetchall()
    conn.close()
    return {
        "total_tickets": total,
        "by_decision": {row["decision"]: row["count"] for row in by_decision},
        "by_category": {row["category"]: row["count"] for row in by_category},
        "tool_calls": {row["tool_name"]: row["count"] for row in tool_calls},
    }


def save_metric(metric_name: str, value: float, labels: str = ""):
    conn = get_conn()
    conn.execute(
        """INSERT INTO metrics (metric_name, labels, value, updated_at)
           VALUES (?, ?, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(metric_name, labels) DO UPDATE SET
           value = value + excluded.value,
           updated_at = CURRENT_TIMESTAMP""",
        (metric_name, labels, value),
    )
    conn.commit()
    conn.close()


def get_metric(metric_name: str, labels: str = "") -> float:
    conn = get_conn()
    row = conn.execute(
        "SELECT value FROM metrics WHERE metric_name = ? AND labels = ?",
        (metric_name, labels),
    ).fetchone()
    conn.close()
    return row[0] if row else 0


def get_all_metrics() -> dict:
    conn = get_conn()
    rows = conn.execute("SELECT metric_name, value FROM metrics").fetchall()
    conn.close()
    result = {}
    for row in rows:
        result[row["metric_name"]] = result.get(row["metric_name"], 0) + row["value"]
    return result


init_db()
