"""
ชั้นเก็บข้อมูล (sqlite3) — รองรับหลายองค์กร (Multi-tenant SaaS)
ตาราง: orgs, users, events, policies, fingerprints  (ทุกข้อมูลผูกกับ org_id)
หลัก PDPA: เก็บเฉพาะ metadata ของเหตุการณ์ (ปรับด้วย SENTINEL_STORE_CONTENT)
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Optional

from .config import settings

_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None


def _connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(settings.db_path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA foreign_keys=ON")
    return _conn


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


SCHEMA = """
CREATE TABLE IF NOT EXISTS orgs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    api_key TEXT UNIQUE NOT NULL,
    plan TEXT DEFAULT 'starter',
    seats INTEGER DEFAULT 5,
    status TEXT DEFAULT 'trial',          -- trial | active | suspended
    quota_month INTEGER DEFAULT 2000,     -- จำนวนการตรวจ AI ต่อเดือน
    valid_until TEXT,                      -- วันหมดอายุ license (ISO)
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id INTEGER NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    name TEXT,
    role TEXT DEFAULT 'admin',            -- admin | platform_admin
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id INTEGER NOT NULL,
    device_id TEXT NOT NULL,               -- ชื่อเครื่อง/asset id
    "user" TEXT, department TEXT, kind TEXT, os TEXT,
    first_seen TEXT, last_seen TEXT, events INTEGER DEFAULT 0,
    UNIQUE(org_id, device_id)
);
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    org_id INTEGER NOT NULL DEFAULT 1,
    ts TEXT NOT NULL,
    user TEXT, department TEXT, device TEXT,
    channel TEXT, destination_url TEXT, action_type TEXT,
    label TEXT, risk_score INTEGER,
    categories TEXT, decision TEXT, reasons TEXT,
    policy_name TEXT, ai_used INTEGER,
    detection_types TEXT, content_excerpt TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_org_ts ON events(org_id, ts);
CREATE TABLE IF NOT EXISTS policies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id INTEGER NOT NULL DEFAULT 1,
    name TEXT NOT NULL, enabled INTEGER DEFAULT 1,
    priority INTEGER DEFAULT 100, rule TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fingerprints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id INTEGER NOT NULL DEFAULT 1,
    name TEXT NOT NULL, label TEXT NOT NULL,
    chunks INTEGER, hashes TEXT NOT NULL, created_at TEXT
);
"""


def _has_column(conn, table: str, col: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == col for r in rows)


def init_db() -> None:
    with _lock:
        conn = _connect()
        conn.executescript(SCHEMA)
        # migration: เพิ่ม org_id ให้ตารางเก่า (ถ้ายังไม่มี)
        for t in ("events", "policies", "fingerprints"):
            try:
                if not _has_column(conn, t, "org_id"):
                    conn.execute(f"ALTER TABLE {t} ADD COLUMN org_id INTEGER NOT NULL DEFAULT 1")
            except sqlite3.OperationalError:
                pass
        # migration: เพิ่มคอลัมน์ license ให้ orgs เก่า
        for col, ddl in (("seats", "INTEGER DEFAULT 5"), ("status", "TEXT DEFAULT 'trial'"),
                         ("quota_month", "INTEGER DEFAULT 2000"), ("valid_until", "TEXT")):
            try:
                if not _has_column(conn, "orgs", col):
                    conn.execute(f"ALTER TABLE orgs ADD COLUMN {col} {ddl}")
            except sqlite3.OperationalError:
                pass
        conn.commit()


# ==================== Orgs ====================
def create_org(name: str, api_key: str, plan: str = "starter", *, seats: int = 5,
               status: str = "trial", quota_month: int = 2000, valid_until: Optional[str] = None) -> int:
    with _lock:
        conn = _connect()
        cur = conn.execute(
            "INSERT INTO orgs (name, api_key, plan, seats, status, quota_month, valid_until, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (name, api_key, plan, seats, status, quota_month, valid_until, now_iso()))
        conn.commit()
        return cur.lastrowid


def get_org_by_api_key(api_key: str) -> Optional[dict]:
    with _lock:
        r = _connect().execute("SELECT * FROM orgs WHERE api_key=?", (api_key,)).fetchone()
    return dict(r) if r else None


def get_org(org_id: int) -> Optional[dict]:
    with _lock:
        r = _connect().execute("SELECT * FROM orgs WHERE id=?", (org_id,)).fetchone()
    return dict(r) if r else None


def count_orgs() -> int:
    with _lock:
        return _connect().execute("SELECT COUNT(*) c FROM orgs").fetchone()["c"]


def update_org_license(org_id: int, *, plan=None, seats=None, status=None,
                       quota_month=None, valid_until=None, name=None) -> bool:
    sets, params = [], []
    for col, val in (("plan", plan), ("seats", seats), ("status", status),
                     ("quota_month", quota_month), ("valid_until", valid_until), ("name", name)):
        if val is not None:
            sets.append(f"{col}=?"); params.append(val)
    if not sets:
        return False
    params.append(org_id)
    with _lock:
        conn = _connect()
        cur = conn.execute(f"UPDATE orgs SET {', '.join(sets)} WHERE id=?", params)
        conn.commit()
        return cur.rowcount > 0


def list_all_orgs() -> list[dict]:
    """สำหรับ Super Admin — ทุก org + จำนวนผู้ใช้/อุปกรณ์/เหตุการณ์."""
    with _lock:
        conn = _connect()
        rows = conn.execute("SELECT * FROM orgs ORDER BY id ASC").fetchall()
        out = []
        for r in rows:
            oid = r["id"]
            users = conn.execute("SELECT COUNT(*) c FROM users WHERE org_id=?", (oid,)).fetchone()["c"]
            devs = conn.execute("SELECT COUNT(*) c FROM devices WHERE org_id=?", (oid,)).fetchone()["c"]
            evs = conn.execute("SELECT COUNT(*) c FROM events WHERE org_id=?", (oid,)).fetchone()["c"]
            blocks = conn.execute("SELECT COUNT(*) c FROM events WHERE org_id=? AND decision='block'", (oid,)).fetchone()["c"]
            d = dict(r)
            d.update(users=users, devices=devs, events=evs, blocks=blocks)
            out.append(d)
    return out


def org_month_events(org_id: int) -> int:
    with _lock:
        return _connect().execute(
            "SELECT COUNT(*) c FROM events WHERE org_id=? AND ts >= strftime('%Y-%m-01', 'now')",
            (org_id,)).fetchone()["c"]


# ==================== Devices (seat enforcement) ====================
def register_device(org_id: int, device_id: str, user: str = "", dept: str = "",
                    kind: str = "browser", os: str = "") -> None:
    if not device_id:
        return
    ts = now_iso()
    with _lock:
        conn = _connect()
        conn.execute(
            """INSERT INTO devices (org_id, device_id, "user", department, kind, os, first_seen, last_seen, events)
               VALUES (?,?,?,?,?,?,?,?,1)
               ON CONFLICT(org_id, device_id) DO UPDATE SET last_seen=excluded.last_seen,
                 events=events+1, "user"=excluded."user", kind=excluded.kind""",
            (org_id, device_id, user, dept, kind, os, ts, ts))
        conn.commit()


def count_devices(org_id: int) -> int:
    with _lock:
        return _connect().execute("SELECT COUNT(*) c FROM devices WHERE org_id=?", (org_id,)).fetchone()["c"]


def device_exists(org_id: int, device_id: str) -> bool:
    with _lock:
        r = _connect().execute("SELECT 1 FROM devices WHERE org_id=? AND device_id=?", (org_id, device_id)).fetchone()
    return r is not None


def list_devices(org_id: int) -> list[dict]:
    with _lock:
        rows = _connect().execute(
            'SELECT id, device_id, "user", department, kind, os, last_seen, events '
            "FROM devices WHERE org_id=? ORDER BY last_seen DESC", (org_id,)).fetchall()
    return [dict(r) for r in rows]


# ==================== Super-admin cross-org feeds ====================
def all_events(limit: int = 100, min_risk: int = 0) -> list[dict]:
    with _lock:
        rows = _connect().execute(
            "SELECT * FROM events WHERE risk_score >= ? ORDER BY ts DESC LIMIT ?",
            (min_risk, limit)).fetchall()
    out = []
    for r in rows:
        e = _row_to_event(r)
        e["org_id"] = r["org_id"]
        out.append(e)
    return out


# ==================== Users ====================
def create_user(org_id: int, email: str, password_hash: str, name: str = "", role: str = "admin") -> int:
    with _lock:
        conn = _connect()
        cur = conn.execute(
            "INSERT INTO users (org_id, email, password_hash, name, role, created_at) VALUES (?,?,?,?,?,?)",
            (org_id, email.lower().strip(), password_hash, name, role, now_iso()))
        conn.commit()
        return cur.lastrowid


def get_user_by_email(email: str) -> Optional[dict]:
    with _lock:
        r = _connect().execute("SELECT * FROM users WHERE email=?", (email.lower().strip(),)).fetchone()
    return dict(r) if r else None


def get_user(user_id: int) -> Optional[dict]:
    with _lock:
        r = _connect().execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return dict(r) if r else None


# ==================== Events ====================
def insert_event(ev: dict[str, Any]) -> None:
    with _lock:
        conn = _connect()
        conn.execute(
            """INSERT OR REPLACE INTO events
            (id, org_id, ts, user, department, device, channel, destination_url, action_type,
             label, risk_score, categories, decision, reasons, policy_name, ai_used,
             detection_types, content_excerpt)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (ev["id"], int(ev.get("org_id", 1)), ev["ts"], ev.get("user", ""), ev.get("department", ""),
             ev.get("device", ""), ev.get("channel", ""), ev.get("destination_url", ""),
             ev.get("action_type", ""), ev.get("label", ""), int(ev.get("risk_score", 0)),
             json.dumps(ev.get("categories", []), ensure_ascii=False),
             ev.get("decision", ""), json.dumps(ev.get("reasons", []), ensure_ascii=False),
             ev.get("policy_name", ""), 1 if ev.get("ai_used") else 0,
             json.dumps(ev.get("detection_types", []), ensure_ascii=False),
             ev.get("content_excerpt")))
        conn.commit()


def _row_to_event(r: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": r["id"], "ts": r["ts"], "user": r["user"] or "",
        "department": r["department"] or "", "device": r["device"] or "",
        "channel": r["channel"] or "", "destination_url": r["destination_url"] or "",
        "action_type": r["action_type"] or "", "label": r["label"] or "Public",
        "risk_score": r["risk_score"] or 0,
        "categories": json.loads(r["categories"] or "[]"),
        "decision": r["decision"] or "monitor",
        "reasons": json.loads(r["reasons"] or "[]"),
        "policy_name": r["policy_name"] or "", "ai_used": bool(r["ai_used"]),
        "detection_types": json.loads(r["detection_types"] or "[]"),
        "content_excerpt": r["content_excerpt"],
    }


def query_events(org_id: int, *, page: int = 1, page_size: int = 25,
                 decision: Optional[str] = None, channel: Optional[str] = None,
                 department: Optional[str] = None, label: Optional[str] = None,
                 search: Optional[str] = None) -> tuple[list[dict], int]:
    where, params = ["org_id = ?"], [org_id]
    if decision:
        where.append("decision = ?"); params.append(decision)
    if channel:
        where.append("channel = ?"); params.append(channel)
    if department:
        where.append("department = ?"); params.append(department)
    if label:
        where.append("label = ?"); params.append(label)
    if search:
        where.append("(user LIKE ? OR reasons LIKE ? OR detection_types LIKE ?)")
        params += [f"%{search}%"] * 3
    clause = "WHERE " + " AND ".join(where)
    with _lock:
        conn = _connect()
        total = conn.execute(f"SELECT COUNT(*) c FROM events {clause}", params).fetchone()["c"]
        rows = conn.execute(
            f"SELECT * FROM events {clause} ORDER BY ts DESC LIMIT ? OFFSET ?",
            [*params, page_size, (page - 1) * page_size]).fetchall()
    return [_row_to_event(r) for r in rows], total


def count_events(org_id: Optional[int] = None) -> int:
    with _lock:
        conn = _connect()
        if org_id is None:
            return conn.execute("SELECT COUNT(*) c FROM events").fetchone()["c"]
        return conn.execute("SELECT COUNT(*) c FROM events WHERE org_id=?", (org_id,)).fetchone()["c"]


def all_events_since(org_id: int, days: int = 30) -> list[dict]:
    with _lock:
        rows = _connect().execute(
            "SELECT * FROM events WHERE org_id=? AND ts >= datetime('now', ?) ORDER BY ts DESC",
            (org_id, f"-{int(days)} days")).fetchall()
    return [_row_to_event(r) for r in rows]


# ==================== Policies ====================
def insert_policy(org_id: int, name: str, enabled: bool, priority: int, rule: dict) -> int:
    with _lock:
        conn = _connect()
        cur = conn.execute(
            "INSERT INTO policies (org_id, name, enabled, priority, rule) VALUES (?,?,?,?,?)",
            (org_id, name, 1 if enabled else 0, priority, json.dumps(rule, ensure_ascii=False)))
        conn.commit()
        return cur.lastrowid


def get_policies(org_id: int) -> list[dict]:
    with _lock:
        rows = _connect().execute(
            "SELECT * FROM policies WHERE org_id=? ORDER BY priority ASC, id ASC", (org_id,)).fetchall()
    return [{"id": r["id"], "name": r["name"], "enabled": bool(r["enabled"]),
             "priority": r["priority"], "rule": json.loads(r["rule"])} for r in rows]


def update_policy(org_id: int, pid: int, name: str, enabled: bool, priority: int, rule: dict) -> bool:
    with _lock:
        conn = _connect()
        cur = conn.execute(
            "UPDATE policies SET name=?, enabled=?, priority=?, rule=? WHERE id=? AND org_id=?",
            (name, 1 if enabled else 0, priority, json.dumps(rule, ensure_ascii=False), pid, org_id))
        conn.commit()
        return cur.rowcount > 0


def delete_policy(org_id: int, pid: int) -> bool:
    with _lock:
        conn = _connect()
        cur = conn.execute("DELETE FROM policies WHERE id=? AND org_id=?", (pid, org_id))
        conn.commit()
        return cur.rowcount > 0


def count_policies(org_id: int) -> int:
    with _lock:
        return _connect().execute("SELECT COUNT(*) c FROM policies WHERE org_id=?", (org_id,)).fetchone()["c"]


# ==================== Fingerprints ====================
def insert_fingerprint(org_id: int, name: str, label: str, chunks: int, hashes: list[int]) -> tuple[int, str]:
    ts = now_iso()
    with _lock:
        conn = _connect()
        cur = conn.execute(
            "INSERT INTO fingerprints (org_id, name, label, chunks, hashes, created_at) VALUES (?,?,?,?,?,?)",
            (org_id, name, label, chunks, json.dumps(hashes), ts))
        conn.commit()
        return cur.lastrowid, ts


def get_fingerprints(org_id: int) -> list[dict]:
    with _lock:
        rows = _connect().execute(
            "SELECT id, name, label, chunks, created_at FROM fingerprints WHERE org_id=? ORDER BY id DESC",
            (org_id,)).fetchall()
    return [dict(r) for r in rows]


def get_all_fingerprints_full() -> list[dict]:
    """โหลดทุก fingerprint ของทุก org เข้าดัชนี (ตอนเริ่มระบบ)."""
    with _lock:
        rows = _connect().execute("SELECT * FROM fingerprints").fetchall()
    return [{"id": r["id"], "org_id": r["org_id"], "name": r["name"], "label": r["label"],
             "chunks": r["chunks"], "hashes": json.loads(r["hashes"])} for r in rows]


def delete_fingerprint(org_id: int, fid: int) -> bool:
    with _lock:
        conn = _connect()
        cur = conn.execute("DELETE FROM fingerprints WHERE id=? AND org_id=?", (fid, org_id))
        conn.commit()
        return cur.rowcount > 0
