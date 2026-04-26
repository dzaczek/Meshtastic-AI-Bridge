"""
node_db.py - Persistent SQLite store for Meshtastic node history.

Keeps signal strength, GPS positions, telemetry and messages for every
node ever seen — far beyond what the device keeps in RAM.

Usage:
    import node_db
    node_db.init()                              # call once at startup
    node_db.upsert_node("abc123", ...)
    node_db.add_signal("abc123", snr=12.5, rssi=-85)
    rows = node_db.get_signal_history("abc123")
"""

import logging
import os
import sqlite3
import threading
import time

logger = logging.getLogger("node_db")

_DB_PATH = os.environ.get("NODE_DB_PATH", os.path.join("data", "mesh_nodes.db"))
_conn: sqlite3.Connection | None = None
_lock = threading.Lock()

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS nodes (
    id         TEXT PRIMARY KEY,
    num        INTEGER,
    long_name  TEXT    DEFAULT '',
    short_name TEXT    DEFAULT '',
    hw_model   TEXT    DEFAULT '',
    role       TEXT    DEFAULT '',
    first_seen REAL    NOT NULL,
    last_seen  REAL    NOT NULL,
    via_mqtt   INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS signal_history (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id   TEXT    NOT NULL,
    ts        REAL    NOT NULL,
    snr       REAL,
    rssi      INTEGER,
    hops_away INTEGER,
    via_mqtt  INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sig ON signal_history(node_id, ts);

CREATE TABLE IF NOT EXISTS position_history (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id TEXT    NOT NULL,
    ts      REAL    NOT NULL,
    lat     REAL    NOT NULL,
    lon     REAL    NOT NULL,
    alt     INTEGER,
    sats    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_pos ON position_history(node_id, ts);

CREATE TABLE IF NOT EXISTS telemetry_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id     TEXT    NOT NULL,
    ts          REAL    NOT NULL,
    battery     INTEGER,
    voltage     REAL,
    uptime_s    INTEGER,
    ch_util     REAL,
    air_util    REAL,
    temperature REAL,
    humidity    REAL,
    pressure    REAL
);
CREATE INDEX IF NOT EXISTS idx_tel ON telemetry_history(node_id, ts);

CREATE TABLE IF NOT EXISTS message_history (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id   TEXT    NOT NULL,
    ts        REAL    NOT NULL,
    direction TEXT    NOT NULL DEFAULT 'rx',
    channel   INTEGER DEFAULT 0,
    text      TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_msg ON message_history(node_id, ts);

CREATE TABLE IF NOT EXISTS traceroutes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         REAL    NOT NULL,
    from_id    TEXT    NOT NULL,
    to_id      TEXT    NOT NULL,
    hops       INTEGER DEFAULT 0,
    route_json TEXT    NOT NULL DEFAULT '[]',
    snr_json   TEXT    NOT NULL DEFAULT '[]',
    channel    INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tr_from ON traceroutes(from_id, ts);
CREATE INDEX IF NOT EXISTS idx_tr_to   ON traceroutes(to_id,   ts);
"""


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

def init(db_path: str | None = None) -> None:
    global _conn, _DB_PATH
    if db_path:
        _DB_PATH = db_path
    parent = os.path.dirname(_DB_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)
    _conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    with _lock, _conn:
        _conn.executescript(_SCHEMA)
    logger.info(f"node_db ready: {_DB_PATH}")


def is_initialized() -> bool:
    return _conn is not None


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------

def upsert_node(node_id: str, num: int | None = None,
                long_name: str = "", short_name: str = "",
                hw_model: str = "", role: str = "",
                via_mqtt: bool = False) -> None:
    if not _conn:
        return
    now = time.time()
    with _lock, _conn:
        _conn.execute("""
            INSERT INTO nodes (id, num, long_name, short_name, hw_model, role,
                               first_seen, last_seen, via_mqtt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                num        = COALESCE(excluded.num,        num),
                long_name  = CASE WHEN excluded.long_name  != '' THEN excluded.long_name  ELSE long_name  END,
                short_name = CASE WHEN excluded.short_name != '' THEN excluded.short_name ELSE short_name END,
                hw_model   = CASE WHEN excluded.hw_model   != '' THEN excluded.hw_model   ELSE hw_model   END,
                role       = CASE WHEN excluded.role       != '' THEN excluded.role       ELSE role       END,
                last_seen  = excluded.last_seen,
                via_mqtt   = excluded.via_mqtt
        """, (node_id, num, long_name, short_name, hw_model, role,
              now, now, int(via_mqtt)))


def add_signal(node_id: str, snr: float | None, rssi: int | None,
               hops_away: int | None = None, via_mqtt: bool = False,
               ts: float | None = None) -> None:
    if not _conn or (snr is None and rssi is None):
        return
    with _lock, _conn:
        _conn.execute(
            "INSERT INTO signal_history (node_id,ts,snr,rssi,hops_away,via_mqtt) VALUES (?,?,?,?,?,?)",
            (node_id, ts or time.time(), snr, rssi, hops_away, int(via_mqtt)),
        )


def add_position(node_id: str, lat: float, lon: float,
                 alt: int | None = None, sats: int | None = None,
                 ts: float | None = None) -> None:
    if not _conn or not lat or not lon:
        return
    # Deduplicate: skip if same coords within last 60 s
    with _lock:
        last = _conn.execute(
            "SELECT lat,lon,ts FROM position_history WHERE node_id=? ORDER BY ts DESC LIMIT 1",
            (node_id,)
        ).fetchone()
        now = ts or time.time()
        if last and abs(last["lat"] - lat) < 1e-5 and abs(last["lon"] - lon) < 1e-5 and (now - last["ts"]) < 60:
            return
        with _conn:
            _conn.execute(
                "INSERT INTO position_history (node_id,ts,lat,lon,alt,sats) VALUES (?,?,?,?,?,?)",
                (node_id, now, lat, lon, alt, sats),
            )


def add_telemetry(node_id: str, battery: int | None = None,
                  voltage: float | None = None, uptime_s: int | None = None,
                  ch_util: float | None = None, air_util: float | None = None,
                  temperature: float | None = None, humidity: float | None = None,
                  pressure: float | None = None, ts: float | None = None) -> None:
    if not _conn:
        return
    # Only store if there's at least one meaningful value
    if all(v is None for v in (battery, voltage, uptime_s, temperature)):
        return
    with _lock, _conn:
        _conn.execute("""
            INSERT INTO telemetry_history
              (node_id,ts,battery,voltage,uptime_s,ch_util,air_util,temperature,humidity,pressure)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (node_id, ts or time.time(), battery, voltage, uptime_s,
              ch_util, air_util, temperature, humidity, pressure))


def add_message(node_id: str, text: str, direction: str = "rx",
                channel: int = 0, ts: float | None = None) -> None:
    if not _conn or not text:
        return
    with _lock, _conn:
        _conn.execute(
            "INSERT INTO message_history (node_id,ts,direction,channel,text) VALUES (?,?,?,?,?)",
            (node_id, ts or time.time(), direction, channel, text),
        )


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

def get_all_nodes(limit: int = 2000) -> list[dict]:
    if not _conn:
        return []
    with _lock:
        rows = _conn.execute(
            "SELECT * FROM nodes ORDER BY last_seen DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_node(node_id: str) -> dict | None:
    if not _conn:
        return None
    with _lock:
        row = _conn.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone()
    return dict(row) if row else None


def get_signal_history(node_id: str, limit: int = 300) -> list[dict]:
    if not _conn:
        return []
    with _lock:
        rows = _conn.execute(
            "SELECT ts,snr,rssi,hops_away,via_mqtt FROM signal_history WHERE node_id=? ORDER BY ts ASC LIMIT ?",
            (node_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_position_history(node_id: str, limit: int = 500) -> list[dict]:
    if not _conn:
        return []
    with _lock:
        rows = _conn.execute(
            "SELECT ts,lat,lon,alt,sats FROM position_history WHERE node_id=? ORDER BY ts ASC LIMIT ?",
            (node_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_telemetry_history(node_id: str, limit: int = 300) -> list[dict]:
    if not _conn:
        return []
    with _lock:
        rows = _conn.execute(
            """SELECT ts,battery,voltage,uptime_s,ch_util,air_util,temperature,humidity,pressure
               FROM telemetry_history WHERE node_id=? ORDER BY ts ASC LIMIT ?""",
            (node_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_message_history(node_id: str, limit: int = 300) -> list[dict]:
    if not _conn:
        return []
    with _lock:
        rows = _conn.execute(
            "SELECT ts,direction,channel,text FROM message_history WHERE node_id=? ORDER BY ts DESC LIMIT ?",
            (node_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


import json as _json


def add_traceroute(from_id: str, to_id: str, hops: int,
                   route: list, snr_towards: list,
                   channel: int = 0, ts: float | None = None) -> None:
    if not _conn:
        return
    ts = ts or time.time()
    with _lock, _conn:
        _conn.execute(
            """INSERT INTO traceroutes (ts,from_id,to_id,hops,route_json,snr_json,channel)
               VALUES (?,?,?,?,?,?,?)""",
            (ts, from_id, to_id, hops,
             _json.dumps(route, ensure_ascii=False),
             _json.dumps(snr_towards),
             channel),
        )


def get_traceroutes(node_id: str, limit: int = 50) -> list[dict]:
    """Return recent traceroutes where node_id is origin, destination, or a hop."""
    if not _conn:
        return []
    with _lock:
        # Simple search: node is from or to
        rows = _conn.execute(
            """SELECT ts, from_id, to_id, hops, route_json, snr_json, channel
               FROM traceroutes
               WHERE from_id=? OR to_id=?
                  OR route_json LIKE ?
               ORDER BY ts DESC LIMIT ?""",
            (node_id, node_id, f'%"{node_id}"%', limit),
        ).fetchall()
    result = []
    for r in rows:
        try:
            route = _json.loads(r["route_json"])
            snr   = _json.loads(r["snr_json"])
        except Exception:
            route, snr = [], []
        result.append({
            "ts":      r["ts"],
            "ts_str":  time.strftime("%Y-%m-%d %H:%M", time.localtime(r["ts"])),
            "from_id": r["from_id"],
            "to_id":   r["to_id"],
            "hops":    r["hops"],
            "route":   route,
            "snr_towards": snr,
            "channel": r["channel"],
        })
    return result


def get_node_stats(node_id: str) -> dict:
    if not _conn:
        return {}
    with _lock:
        sig = _conn.execute("""
            SELECT COUNT(*) as cnt,
                   ROUND(AVG(snr),1) as avg_snr, MIN(snr) as min_snr, MAX(snr) as max_snr,
                   ROUND(AVG(rssi)) as avg_rssi, MIN(rssi) as min_rssi, MAX(rssi) as max_rssi
            FROM signal_history WHERE node_id=?
        """, (node_id,)).fetchone()
        msg_cnt = _conn.execute(
            "SELECT COUNT(*) FROM message_history WHERE node_id=?", (node_id,)
        ).fetchone()[0]
        pos_cnt = _conn.execute(
            "SELECT COUNT(*) FROM position_history WHERE node_id=?", (node_id,)
        ).fetchone()[0]
        tel_cnt = _conn.execute(
            "SELECT COUNT(*) FROM telemetry_history WHERE node_id=?", (node_id,)
        ).fetchone()[0]
        last_bat = _conn.execute(
            "SELECT battery,voltage FROM telemetry_history WHERE node_id=? AND battery IS NOT NULL ORDER BY ts DESC LIMIT 1",
            (node_id,)
        ).fetchone()
    return {
        "packets":       int(sig["cnt"]) if sig else 0,
        "avg_snr":       sig["avg_snr"]  if sig else None,
        "min_snr":       sig["min_snr"]  if sig else None,
        "max_snr":       sig["max_snr"]  if sig else None,
        "avg_rssi":      sig["avg_rssi"] if sig else None,
        "min_rssi":      sig["min_rssi"] if sig else None,
        "max_rssi":      sig["max_rssi"] if sig else None,
        "messages":      int(msg_cnt),
        "positions":     int(pos_cnt),
        "telemetry_pts": int(tel_cnt),
        "last_battery":  dict(last_bat) if last_bat else None,
    }
