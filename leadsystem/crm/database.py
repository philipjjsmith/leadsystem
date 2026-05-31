"""
CRM database layer — auto-detects backend:
  DATABASE_URL not set  →  SQLite  (local dev, zero changes needed)
  DATABASE_URL set      →  PostgreSQL via psycopg2  (Render + Supabase)

psycopg2 is imported lazily inside _conn() so the local install never
needs it.  On Render, the build command installs psycopg2-binary.

Re-importing a scan updates scan data but never overwrites:
  status, notes, follow_up_date, deal_value, contact history.
"""

import json
import os
from datetime import datetime

DATABASE_URL = os.environ.get("DATABASE_URL", "")
USE_PG       = bool(DATABASE_URL)

_SQLITE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "output", "leadsystem.db"
)

STATUSES = ["new", "called", "interested", "proposal", "closed", "lost"]
METHODS  = ["call", "email", "sms", "in-person", "other"]
OUTCOMES = ["no-answer", "left-vm", "not-interested", "interested", "proposal-sent", "closed"]


# ── Connection factory ──────────────────────────────────────────────────────────

def _conn():
    if USE_PG:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(DATABASE_URL)
        conn.cursor_factory = psycopg2.extras.RealDictCursor
        return conn
    else:
        import sqlite3
        os.makedirs(os.path.dirname(_SQLITE_PATH), exist_ok=True)
        conn = sqlite3.connect(_SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn


def _sql(q: str) -> str:
    """Translate ? → %s when targeting PostgreSQL."""
    return q.replace("?", "%s") if USE_PG else q


def _exec(conn, sql: str, params=()):
    """
    Execute a single SQL statement.
    SQLite3: execute directly on the connection (returns cursor).
    psycopg2: open a new cursor, execute, return it.
    """
    sql = _sql(sql)
    if USE_PG:
        cur = conn.cursor()
        cur.execute(sql, params or ())
        return cur
    else:
        return conn.execute(sql, params)


def _fetchall(conn, sql: str, params=()) -> list:
    cur = _exec(conn, sql, params)
    rows = cur.fetchall()
    return [dict(r) for r in rows]


def _fetchone(conn, sql: str, params=()):
    cur = _exec(conn, sql, params)
    row = cur.fetchone()
    return dict(row) if row else None


# ── Schema ──────────────────────────────────────────────────────────────────────

_LEADS_DDL = """
    CREATE TABLE IF NOT EXISTS leads (
        id              {serial}    PRIMARY KEY,
        place_id        TEXT        UNIQUE NOT NULL,
        name            TEXT        NOT NULL,
        address         TEXT        DEFAULT '',
        phone           TEXT        DEFAULT '',
        website         TEXT        DEFAULT '',
        has_website     INTEGER     DEFAULT 0,
        rating          REAL        DEFAULT 0,
        review_count    INTEGER     DEFAULT 0,
        niche_key       TEXT        DEFAULT '',
        city            TEXT        DEFAULT '',
        warmth_score    INTEGER     DEFAULT 0,
        tier            INTEGER     DEFAULT 4,
        tier_label      TEXT        DEFAULT '',
        score_breakdown TEXT        DEFAULT '{{}}',
        website_issues  TEXT        DEFAULT '[]',
        google_maps_url TEXT        DEFAULT '',
        has_facebook    INTEGER     DEFAULT 0,
        facebook_url    TEXT        DEFAULT '',
        has_instagram   INTEGER     DEFAULT 0,
        instagram_url   TEXT        DEFAULT '',
        budget_tier     TEXT        DEFAULT '',
        mobile_score    INTEGER     DEFAULT -1,
        status          TEXT        DEFAULT 'new',
        notes           TEXT        DEFAULT '',
        follow_up_date  TEXT,
        deal_value      REAL        DEFAULT 0,
        contacted_at    TEXT,
        closed_at       TEXT,
        scan_date       TEXT,
        created_at      TEXT        NOT NULL,
        updated_at      TEXT        NOT NULL
    )
"""

_LOG_DDL = """
    CREATE TABLE IF NOT EXISTS contact_log (
        id        {serial}  PRIMARY KEY,
        lead_id   INTEGER   NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        logged_at TEXT      NOT NULL,
        method    TEXT      NOT NULL,
        outcome   TEXT      NOT NULL,
        notes     TEXT      DEFAULT ''
    )
"""


def init_db() -> None:
    """Create tables and indexes if they don't exist. Safe to call every startup."""
    serial = "SERIAL" if USE_PG else "INTEGER AUTOINCREMENT"
    # SQLite uses INTEGER PRIMARY KEY (implicit rowid alias), not INTEGER AUTOINCREMENT
    serial = "SERIAL" if USE_PG else "INTEGER"

    conn = _conn()

    stmts = [
        _LEADS_DDL.format(serial=serial),
        _LOG_DDL.format(serial=serial),
        "CREATE INDEX IF NOT EXISTS idx_leads_status    ON leads(status)",
        "CREATE INDEX IF NOT EXISTS idx_leads_tier      ON leads(tier)",
        "CREATE INDEX IF NOT EXISTS idx_leads_follow_up ON leads(follow_up_date)",
        "CREATE INDEX IF NOT EXISTS idx_log_lead        ON contact_log(lead_id)",
    ]

    if USE_PG:
        cur = conn.cursor()
        for stmt in stmts:
            cur.execute(stmt)
        conn.commit()
        cur.close()
    else:
        for stmt in stmts:
            conn.execute(stmt)
        conn.commit()
        # Non-destructive migration: add mobile_score column if missing
        try:
            conn.execute("ALTER TABLE leads ADD COLUMN mobile_score INTEGER DEFAULT 0")
            conn.commit()
        except Exception:
            pass

    conn.close()


# ── Lead import ─────────────────────────────────────────────────────────────────

def import_leads(leads: list) -> dict:
    """
    Bulk-import leads from a scan JSON list.
    Returns {imported, updated, skipped}.
    Existing leads: scan data updated, CRM fields preserved.
    """
    init_db()
    conn      = _conn()
    stats     = {"imported": 0, "updated": 0, "skipped": 0}
    scan_date = datetime.now().isoformat()
    now       = scan_date

    for lead in leads:
        place_id = lead.get("place_id", "").strip()
        if not place_id:
            stats["skipped"] += 1
            continue

        existing = _fetchone(conn, "SELECT id FROM leads WHERE place_id = ?", (place_id,))

        # Extract mobile score.  -1 = no audit ran (no website / audit skipped).
        # 0 is a valid real score (PageSpeed gave 0/100), so we can't use 0 as sentinel.
        _ws = lead.get("website_score") or {}
        if isinstance(_ws, dict) and _ws:
            _ms_val = _ws.get("mobile_performance")
            _mobile = int(_ms_val) if isinstance(_ms_val, int) else -1
        else:
            _mobile = -1

        scan_fields = (
            lead.get("name") or "",
            lead.get("address") or "",
            lead.get("phone") or "",
            lead.get("website") or "",
            int(bool(lead.get("has_website"))),
            lead.get("rating") or 0,
            lead.get("review_count") or 0,
            lead.get("niche_key") or "",
            lead.get("city") or "",
            lead.get("warmth_score") or 0,
            lead.get("tier") or 4,
            lead.get("tier_label") or "",
            json.dumps(lead.get("score_breakdown") or {}),
            json.dumps(lead.get("website_issues") or []),
            lead.get("google_maps_url") or "",
            int(bool(lead.get("has_facebook"))),
            lead.get("facebook_url") or "",
            int(bool(lead.get("has_instagram"))),
            lead.get("instagram_url") or "",
            lead.get("budget_tier") or "",
            _mobile,
        )

        if existing:
            _exec(conn, """
                UPDATE leads SET
                    name=?, address=?, phone=?, website=?, has_website=?,
                    rating=?, review_count=?, niche_key=?, city=?,
                    warmth_score=?, tier=?, tier_label=?, score_breakdown=?,
                    website_issues=?, google_maps_url=?, has_facebook=?,
                    facebook_url=?, has_instagram=?, instagram_url=?,
                    budget_tier=?, mobile_score=?, scan_date=?, updated_at=?
                WHERE place_id=?
            """, (*scan_fields, scan_date, now, place_id))
            stats["updated"] += 1
        else:
            _exec(conn, """
                INSERT INTO leads (
                    place_id, name, address, phone, website, has_website,
                    rating, review_count, niche_key, city, warmth_score, tier,
                    tier_label, score_breakdown, website_issues, google_maps_url,
                    has_facebook, facebook_url, has_instagram, instagram_url,
                    budget_tier, mobile_score, status, notes, scan_date, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'new','',?,?,?)
            """, (place_id, *scan_fields, scan_date, now, now))
            stats["imported"] += 1

    if USE_PG:
        conn.commit()
    else:
        conn.commit()
    conn.close()
    return stats


# ── Queries ─────────────────────────────────────────────────────────────────────

def get_leads(status=None, tier=None, city=None, niche=None, no_website=False) -> list[dict]:
    conn = _conn()
    q = "SELECT * FROM leads WHERE 1=1"
    p: list = []
    if status:
        q += " AND status=?"; p.append(status)
    if tier:
        q += " AND tier=?"; p.append(tier)
    if city:
        q += " AND city LIKE ?"; p.append(f"%{city}%")
    if niche:
        q += " AND niche_key=?"; p.append(niche)
    if no_website:
        q += " AND has_website=0"
    q += " ORDER BY warmth_score DESC, review_count DESC"
    rows = _fetchall(conn, q, p)
    conn.close()
    return rows


def get_lead(lead_id: int) -> dict | None:
    conn = _conn()
    row  = _fetchone(conn, "SELECT * FROM leads WHERE id=?", (lead_id,))
    conn.close()
    return row


def update_lead(lead_id: int, **fields) -> bool:
    """Update CRM fields only. Ignores non-CRM field names."""
    allowed = {"status", "notes", "follow_up_date", "deal_value", "contacted_at", "closed_at"}
    safe = {k: v for k, v in fields.items() if k in allowed}
    if not safe:
        return False
    safe["updated_at"] = datetime.now().isoformat()
    clause = ", ".join(f"{k}=?" for k in safe)
    conn = _conn()
    _exec(conn, f"UPDATE leads SET {clause} WHERE id=?", (*safe.values(), lead_id))
    conn.commit()
    conn.close()
    return True


def log_contact(lead_id: int, method: str, outcome: str, notes: str = "") -> int:
    """Add a contact log entry. Sets contacted_at on the lead if not already set."""
    now  = datetime.now().isoformat()
    conn = _conn()

    _exec(conn,
        "UPDATE leads SET contacted_at=COALESCE(contacted_at,?), updated_at=? WHERE id=?",
        (now, now, lead_id)
    )

    if USE_PG:
        cur = conn.cursor()
        cur.execute(
            _sql("INSERT INTO contact_log (lead_id, logged_at, method, outcome, notes)"
                 " VALUES (?,?,?,?,?) RETURNING id"),
            (lead_id, now, method, outcome, notes)
        )
        log_id = cur.fetchone()["id"]
    else:
        cur = conn.execute(
            "INSERT INTO contact_log (lead_id, logged_at, method, outcome, notes) VALUES (?,?,?,?,?)",
            (lead_id, now, method, outcome, notes)
        )
        log_id = cur.lastrowid

    conn.commit()
    conn.close()
    return log_id


def get_contact_log(lead_id: int) -> list[dict]:
    conn = _conn()
    rows = _fetchall(conn,
        "SELECT * FROM contact_log WHERE lead_id=? ORDER BY logged_at DESC",
        (lead_id,)
    )
    conn.close()
    return rows


def get_follow_ups() -> list[dict]:
    """All leads with a follow-up date set that aren't closed or lost."""
    conn = _conn()
    rows = _fetchall(conn, """
        SELECT * FROM leads
        WHERE follow_up_date IS NOT NULL
          AND status NOT IN ('closed','lost')
        ORDER BY follow_up_date ASC
    """)
    conn.close()
    return rows


def get_pipeline_stats() -> dict:
    conn = _conn()

    by_status = {
        row["status"]: row["count"]
        for row in _fetchall(conn,
            "SELECT status, COUNT(*) as count FROM leads GROUP BY status"
        )
    }

    closed   = _fetchone(conn,
        "SELECT COALESCE(SUM(deal_value),0) as total, COUNT(*) as count FROM leads WHERE status='closed'"
    )
    pipeline = _fetchone(conn,
        "SELECT COALESCE(SUM(deal_value),0) as total, COUNT(*) as count FROM leads"
        " WHERE status IN ('interested','proposal')"
    )
    total     = (_fetchone(conn, "SELECT COUNT(*) as c FROM leads") or {}).get("c", 0)
    contacted = (_fetchone(conn,
        "SELECT COUNT(*) as c FROM leads WHERE status NOT IN ('new','lost')"
    ) or {}).get("c", 0)

    conn.close()

    closed_count  = int(closed["count"] or 0)
    closed_total  = float(closed["total"] or 0)
    denominator   = contacted + closed_count

    return {
        "by_status":      by_status,
        "closed_count":   closed_count,
        "closed_total":   closed_total,
        "pipeline_count": int(pipeline["count"] or 0),
        "pipeline_total": float(pipeline["total"] or 0),
        "total":          total,
        "contacted":      contacted,
        "close_rate":     round(closed_count / denominator * 100, 1) if denominator else 0.0,
        "avg_deal":       round(closed_total / closed_count, 2) if closed_count else 0.0,
    }


def total_leads() -> int:
    try:
        conn = _conn()
        row  = _fetchone(conn, "SELECT COUNT(*) as c FROM leads")
        conn.close()
        return int(row["c"]) if row else 0
    except Exception:
        return 0
