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

CREATE TABLE IF NOT EXISTS net_snapshots (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id   TEXT    NOT NULL,
    ts        REAL    NOT NULL,
    source    TEXT    NOT NULL DEFAULT 'liamcottle',
    data_json TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_net_snap ON net_snapshots(node_id, ts);

CREATE TABLE IF NOT EXISTS packets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          REAL    NOT NULL,
    from_id     TEXT    NOT NULL,
    to_id       TEXT    NOT NULL,
    channel     INTEGER DEFAULT 0,
    portnum     TEXT    NOT NULL,
    encrypted   INTEGER DEFAULT 0,
    via_mqtt    INTEGER DEFAULT 0,
    packet_json TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_packets_ts ON packets(ts);
CREATE INDEX IF NOT EXISTS idx_packets_from ON packets(from_id);
CREATE INDEX IF NOT EXISTS idx_packets_to ON packets(to_id);

CREATE TABLE IF NOT EXISTS ai_token_usage (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         REAL    NOT NULL,
    node_id    TEXT    NOT NULL,
    tokens_in  INTEGER NOT NULL,
    tokens_out INTEGER NOT NULL,
    category   TEXT    NOT NULL DEFAULT 'chat',
    model      TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_ai_tokens_ts   ON ai_token_usage(ts);
CREATE INDEX IF NOT EXISTS idx_ai_tokens_node ON ai_token_usage(node_id);

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
        # Migrate BEFORE executescript so new indexes on new columns work
        try:
            cols = {r[1] for r in _conn.execute("PRAGMA table_info(ai_token_usage)").fetchall()}
            if cols and 'category' not in cols:
                _conn.execute("ALTER TABLE ai_token_usage ADD COLUMN category TEXT NOT NULL DEFAULT 'chat'")
            if cols and 'model' not in cols:
                _conn.execute("ALTER TABLE ai_token_usage ADD COLUMN model TEXT NOT NULL DEFAULT ''")
        except Exception:
            pass
        try:
            pkt_cols = {r[1] for r in _conn.execute("PRAGMA table_info(packets)").fetchall()}
            if pkt_cols and 'via_mqtt' not in pkt_cols:
                _conn.execute("ALTER TABLE packets ADD COLUMN via_mqtt INTEGER DEFAULT 0")
        except Exception:
            pass
        _conn.executescript(_SCHEMA)
        # Create category index separately (safe after schema + migration)
        _conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_tokens_cat ON ai_token_usage(category)")
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


def get_node_packet_counts(hours: float = 168.0, no_mqtt: bool = True) -> dict:
    """Return {node_id: packet_count} for all radio nodes in the time window."""
    if not _conn:
        return {}
    import time
    cutoff = time.time() - hours * 3600.0
    mq_and = "AND via_mqtt = 0" if no_mqtt else ""
    with _lock:
        rows = _conn.execute(
            f"""SELECT from_id, COUNT(*) as cnt
                FROM packets
                WHERE ts >= ? AND from_id != '?' {mq_and}
                GROUP BY from_id""",
            (cutoff,),
        ).fetchall()
    return {r[0]: r[1] for r in rows}


def get_hop_reachability(hours: float = 4.0, no_mqtt: bool = True) -> dict:
    """Return time-series node-reachability per hop count (0-7).

    Result:
      {
        "buckets":      ["14:00", "14:15", ...],   # time labels
        "series":       [{"hop": 0, "counts": [3, 2, ...]}, ...],
        "bucket_label": "15m"
      }
    Each count = distinct nodes seen at that hop distance in that time bucket.
    """
    if not _conn:
        return {}
    import time as _time
    cutoff = _time.time() - hours * 3600.0
    # Use finer resolution than the global _bucket_config for this chart:
    # 1-minute buckets for ≤1h, 5m for ≤3h, 10m for ≤6h, then standard.
    if   hours <= 1:   bucket_secs, sqlite_fmt, label = 60,       '%H:%M',     '1m'
    elif hours <= 3:   bucket_secs, sqlite_fmt, label = 5*60,     '%H:%M',     '5m'
    elif hours <= 6:   bucket_secs, sqlite_fmt, label = 10*60,    '%H:%M',     '10m'
    else:              bucket_secs, sqlite_fmt, label = _bucket_config(hours)
    mq_and = "AND via_mqtt = 0" if no_mqtt else ""
    with _lock:
        rows = _conn.execute(
            f"""SELECT
                    strftime(?, datetime(
                        CAST(ts/{bucket_secs} AS INTEGER)*{bucket_secs},
                        'unixepoch','localtime')) AS b,
                    hops_away,
                    COUNT(DISTINCT node_id) AS cnt
                FROM signal_history
                WHERE ts >= ? AND hops_away IS NOT NULL
                    AND hops_away BETWEEN 0 AND 7
                    {mq_and}
                GROUP BY b, hops_away
                ORDER BY b, hops_away""",
            [sqlite_fmt, cutoff],
        ).fetchall()

    from collections import defaultdict, OrderedDict
    data: dict = defaultdict(lambda: defaultdict(int))
    bucket_order: list = []
    for b, hop, cnt in rows:
        if b and b not in bucket_order:
            bucket_order.append(b)
        if b:
            data[b][int(hop)] = cnt

    series = []
    for h in range(8):
        counts = [data[b].get(h, 0) for b in bucket_order]
        if any(c > 0 for c in counts):
            series.append({"hop": h, "counts": counts})

    return {"buckets": bucket_order, "series": series, "bucket_label": label}


def get_avg_hops_per_node(hours: float = 168.0, no_mqtt: bool = True) -> dict:
    """Return {node_id: avg_hops_away} for all nodes seen within the time window.
    Uses average hop count so a node observed at 6 and 7 hops yields 6.5,
    placing its dot between the two rings on the radial chart."""
    if not _conn:
        return {}
    import time
    cutoff = time.time() - hours * 3600.0
    mq_and = "AND via_mqtt = 0" if no_mqtt else ""
    with _lock:
        rows = _conn.execute(
            f"""SELECT node_id, AVG(hops_away), COUNT(*)
                FROM signal_history
                WHERE ts >= ? AND hops_away IS NOT NULL {mq_and}
                GROUP BY node_id""",
            (cutoff,),
        ).fetchall()
    return {r[0]: round(r[1], 2) for r in rows}


def get_signal_history(node_id: str, limit: int = 300) -> list[dict]:
    if not _conn:
        return []
    with _lock:
        rows = _conn.execute(
            "SELECT ts,snr,rssi,hops_away,via_mqtt FROM signal_history WHERE node_id=? ORDER BY ts ASC LIMIT ?",
            (node_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_latest_signal(node_id: str) -> dict | None:
    """Return the most recent signal_history row for a node, or None."""
    if not _conn:
        return None
    with _lock:
        row = _conn.execute(
            "SELECT ts,snr,rssi,hops_away,via_mqtt FROM signal_history "
            "WHERE node_id=? ORDER BY ts DESC LIMIT 1",
            (node_id,),
        ).fetchone()
    return dict(row) if row else None


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


def add_ai_token_usage(tokens_in: int, tokens_out: int, node_id: str,
                       ts: float | None = None,
                       category: str = 'chat',
                       model: str = '') -> None:
    if not _conn:
        return
    ts = ts or time.time()
    with _lock, _conn:
        _conn.execute(
            "INSERT INTO ai_token_usage (ts, node_id, tokens_in, tokens_out, category, model) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (ts, node_id, tokens_in, tokens_out, category, model)
        )


def get_token_by_category(days: int = 30) -> list:
    """Returns token usage grouped by category for the last N days."""
    if not _conn:
        return []
    since = time.time() - days * 86400
    with _lock:
        rows = _conn.execute(
            """SELECT category,
                      SUM(tokens_in)  as tin,
                      SUM(tokens_out) as tout
               FROM ai_token_usage
               WHERE ts > ?
               GROUP BY category
               ORDER BY (tin + tout) DESC""",
            (since,)
        ).fetchall()
    return [{"category": r[0], "tokens_in": r[1] or 0, "tokens_out": r[2] or 0} for r in rows]

def get_token_stats() -> dict:
    """Returns AI token usage statistics over the last month, weekly, and daily breakdowns."""
    if not _conn:
        return {}

    now = time.time()
    one_month_ago = now - (30 * 24 * 3600)

    with _lock:
        # Total lifetime tokens
        total_row = _conn.execute(
            "SELECT SUM(tokens_in), SUM(tokens_out) FROM ai_token_usage"
        ).fetchone()

        # Total tokens this month
        month_row = _conn.execute(
            """SELECT SUM(tokens_in), SUM(tokens_out)
               FROM ai_token_usage
               WHERE ts > ?""",
            (one_month_ago,)
        ).fetchone()
        month_in = month_row[0] or 0
        month_out = month_row[1] or 0

        # Daily breakdown for the last 7 days
        seven_days_ago = now - (7 * 24 * 3600)
        daily_rows = _conn.execute(
            """SELECT
                 strftime('%Y-%m-%d', datetime(ts, 'unixepoch', 'localtime')) as day,
                 SUM(tokens_in), SUM(tokens_out)
               FROM ai_token_usage
               WHERE ts > ?
               GROUP BY day
               ORDER BY day ASC""",
            (seven_days_ago,)
        ).fetchall()

        daily = []
        for r in daily_rows:
            daily.append({
                "label": r[0],
                "tokens_in": r[1] or 0,
                "tokens_out": r[2] or 0
            })

        # Top users (by node_id) this month
        top_users_rows = _conn.execute(
            """SELECT node_id, SUM(tokens_in + tokens_out) as total
               FROM ai_token_usage
               WHERE ts > ?
               GROUP BY node_id
               ORDER BY total DESC
               LIMIT 10""",
            (one_month_ago,)
        ).fetchall()

        top_users = []
        for r in top_users_rows:
            top_users.append({
                "node_id": r[0],
                "total_tokens": r[1] or 0
            })

    return {
        "total": {"tokens_in": total_row[0] or 0, "tokens_out": total_row[1] or 0},
        "month": {"tokens_in": month_in, "tokens_out": month_out},
        "daily": daily,
        "top_users": top_users
    }

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


def add_net_snapshot(node_id: str, data: dict, source: str = "liamcottle") -> None:
    """Save a net-fetched snapshot for a node (full JSON blob + extracted telemetry/position)."""
    if not _conn:
        return
    import json as _json
    ts = time.time()
    with _lock:
        _conn.execute(
            "INSERT INTO net_snapshots (node_id, ts, source, data_json) VALUES (?,?,?,?)",
            (node_id.lower(), ts, source, _json.dumps(data, ensure_ascii=False))
        )
        _conn.commit()

    # Also persist extracted fields into dedicated history tables
    try:
        bat  = data.get("battery_level")
        volt = data.get("voltage")
        upt  = data.get("uptime_seconds")
        ch   = data.get("channel_utilization")
        air  = data.get("air_util_tx")
        temp = data.get("temperature")
        hum  = data.get("relative_humidity")
        pres = data.get("barometric_pressure")
        if any(v is not None for v in [bat, volt, upt, ch, air, temp, hum, pres]):
            add_telemetry(node_id, battery=bat,
                          voltage=float(volt) if volt is not None else None,
                          uptime_s=int(upt) if upt else None,
                          ch_util=float(ch) if ch is not None else None,
                          air_util=float(air) if air is not None else None,
                          temperature=float(temp) if temp is not None else None,
                          humidity=float(hum) if hum is not None else None,
                          pressure=float(pres) if pres is not None else None)
    except Exception:
        pass
    try:
        lat = data.get("latitude")
        lon = data.get("longitude")
        alt = data.get("altitude")
        if lat and lon:
            add_position(node_id, lat=float(lat), lon=float(lon),
                         altitude=int(alt) if alt else None)
    except Exception:
        pass


def get_net_snapshots(node_id: str, limit: int = 50) -> list[dict]:
    """Return net snapshots for a node, newest first."""
    if not _conn:
        return []
    import json as _json
    with _lock:
        rows = _conn.execute(
            "SELECT ts, source, data_json FROM net_snapshots WHERE node_id=? ORDER BY ts DESC LIMIT ?",
            (node_id.lower(), limit)
        ).fetchall()
    result = []
    for r in rows:
        try:
            data = _json.loads(r["data_json"])
        except Exception:
            data = {}
        result.append({"ts": r["ts"], "source": r["source"], "data": data})
    return result


def add_packet_record(parsed: dict) -> None:
    """Insert a raw packet record for analytics, pruning to keep records from the last 30 days."""
    if not _conn:
        return
    import json as _json
    import time
    try:
        ts = parsed.get("ts", time.time())
        from_id = parsed.get("from_id", "?")
        to_id = parsed.get("to_id", "?")
        channel = parsed.get("channel", 0)
        portnum = parsed.get("portnum_raw", "UNKNOWN")
        encrypted = 1 if parsed.get("encrypted") else 0
        via_mqtt = 1 if parsed.get("via_mqtt") else 0
        pkt_json = _json.dumps(parsed, ensure_ascii=False)
    except Exception:
        return

    with _lock, _conn:
        _conn.execute(
            """INSERT INTO packets (ts, from_id, to_id, channel, portnum, encrypted, via_mqtt, packet_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (ts, from_id, to_id, channel, portnum, encrypted, via_mqtt, pkt_json)
        )

        # Prune older than 30 days. Do it ~1% of the time to avoid lag on every message.
        import random
        if random.random() < 0.01:
            cutoff_ts = time.time() - (30 * 24 * 60 * 60)
            _conn.execute(
                "DELETE FROM packets WHERE ts < ?", (cutoff_ts,)
            )


def _bucket_config(hours: float) -> tuple:
    """Return (bucket_seconds, sqlite_fmt, label_suffix) based on time range."""
    if hours <= 1:    return (5  * 60,   '%H:%M',    '5m')
    if hours <= 3:    return (10 * 60,   '%H:%M',    '10m')
    if hours <= 6:    return (15 * 60,   '%H:%M',    '15m')
    if hours <= 24:   return (60 * 60,   '%H:00',    '1h')
    if hours <= 72:   return (6  * 3600, '%d/%m %Hh','6h')
    if hours <= 336:  return (24 * 3600, '%m-%d',    '1d')
    return              (7  * 86400, '%m-%d',    '1w')


def _build_hourly(conn, start_ts: float, hours: float, pf_and: str, hb_and: str,
                  params: list) -> tuple:
    """Return (buckets_list, bucket_label_str) with adaptive time resolution."""
    bucket_secs, sqlite_fmt, label = _bucket_config(hours)
    sql = f"""
        SELECT strftime(?, datetime(
               CAST(ts/{bucket_secs} AS INTEGER)*{bucket_secs},
               'unixepoch','localtime')) AS b,
               COUNT(*) AS c
        FROM packets WHERE ts > ? {pf_and} {hb_and}
        GROUP BY b ORDER BY b
    """
    rows = conn.execute(sql, [sqlite_fmt] + params).fetchall()
    buckets = [{"label": r[0] or "?", "count": r[1]} for r in rows if r[0]]
    return buckets, label


def get_packet_analytics(hours: float = 168.0, portnum_filter: str = None,
                         hide_broadcast: bool = False, no_mqtt: bool = True) -> dict:
    """Return aggregated packet analytics for the last `hours` hours."""
    if not _conn:
        return {}

    import time
    start_ts = time.time() - (hours * 3600.0)
    pf = portnum_filter
    pf_and  = "AND portnum = ?" if pf else ""
    hb_and  = "AND to_id NOT IN ('broadcast','ffffffff')" if hide_broadcast else ""
    mq_and  = "AND via_mqtt = 0" if no_mqtt else ""
    pf_p = lambda base: base + ([pf] if pf else [])

    with _lock:
        total_info = _conn.execute(
            f"SELECT COUNT(*), SUM(CASE WHEN encrypted=1 THEN 1 ELSE 0 END) FROM packets WHERE ts > ? {pf_and} {hb_and} {mq_and}",
            pf_p([start_ts])
        ).fetchone()
        total_packets = total_info[0] or 0
        total_encrypted = total_info[1] or 0

        # Combine all filters for _build_hourly
        all_and = f"{pf_and} {hb_and} {mq_and}"
        hourly, bucket_label = _build_hourly(
            _conn, start_ts, hours, all_and, "", pf_p([start_ts])
        )

        top_senders = _conn.execute(
            f"""SELECT from_id, COUNT(*) as cnt FROM packets
               WHERE ts > ? AND from_id != '?' {pf_and} {hb_and} {mq_and}
               GROUP BY from_id ORDER BY cnt DESC LIMIT 10""",
            pf_p([start_ts])
        ).fetchall()

        # All unicast links
        top_links = _conn.execute(
            f"""SELECT from_id, to_id, COUNT(*) as cnt FROM packets
               WHERE ts > ? AND from_id != '?' AND to_id NOT IN ('?', 'broadcast', 'ffffffff') {mq_and}
               GROUP BY from_id, to_id ORDER BY cnt DESC LIMIT 500""",
            (start_ts,)
        ).fetchall()

        # Text-only P2P links
        top_links_text = _conn.execute(
            f"""SELECT from_id, to_id, COUNT(*) as cnt FROM packets
               WHERE ts > ? AND from_id != '?' AND to_id NOT IN ('?', 'broadcast', 'ffffffff')
               AND portnum = 'TEXT_MESSAGE_APP' {mq_and}
               GROUP BY from_id, to_id ORDER BY cnt DESC LIMIT 500""",
            (start_ts,)
        ).fetchall()

        # Available portnum types for filter
        portnum_types = _conn.execute(
            f"SELECT DISTINCT portnum FROM packets WHERE ts > ? {mq_and} ORDER BY portnum",
            (start_ts,)
        ).fetchall()

        encrypted_senders = _conn.execute(
            f"""SELECT from_id, COUNT(*) as cnt FROM packets
               WHERE ts > ? AND from_id != '?' AND encrypted=1 {pf_and} {mq_and}
               GROUP BY from_id ORDER BY cnt DESC LIMIT 100""",
            pf_p([start_ts])
        ).fetchall()

        encrypted_links = _conn.execute(
            f"""SELECT from_id, to_id, COUNT(*) as cnt FROM packets
               WHERE ts > ? AND from_id != '?' AND to_id NOT IN ('?', 'broadcast', 'ffffffff') AND encrypted=1 {mq_and}
               GROUP BY from_id, to_id ORDER BY cnt DESC LIMIT 100""",
            (start_ts,)
        ).fetchall()

        # Get positions of top senders to use in heatmap
        node_positions = _conn.execute(
            """SELECT node_id, lat, lon FROM position_history
               WHERE id IN (
                   SELECT MAX(id) FROM position_history GROUP BY node_id
               )
            """
        ).fetchall()
        positions_map = {r[0]: {"lat": r[1], "lon": r[2]} for r in node_positions}

        dest_stats = _conn.execute(
            f"""SELECT
               SUM(CASE WHEN to_id IN ('broadcast', 'ffffffff') THEN 1 ELSE 0 END) as broadcast_cnt,
               SUM(CASE WHEN to_id NOT IN ('broadcast', 'ffffffff') AND to_id != '?' THEN 1 ELSE 0 END) as private_cnt
               FROM packets WHERE ts > ? {pf_and} {hb_and} {mq_and}""",
            pf_p([start_ts])
        ).fetchone()
        broadcast_cnt = dest_stats[0] or 0
        private_cnt = dest_stats[1] or 0

        top_types = _conn.execute(
            f"SELECT portnum, COUNT(*) as cnt FROM packets WHERE ts > ? {mq_and} GROUP BY portnum ORDER BY cnt DESC LIMIT 20",
            (start_ts,)
        ).fetchall()

    return {
        "total": total_packets,
        "encrypted": total_encrypted,
        "plaintext": total_packets - total_encrypted,
        "hourly": hourly,
        "bucket_label": bucket_label,
        "top_senders": [{"id": r[0], "count": r[1]} for r in top_senders],
        "top_links":      [{"from": r[0], "to": r[1], "count": r[2]} for r in top_links],
        "top_links_text": [{"from": r[0], "to": r[1], "count": r[2]} for r in top_links_text],
        "encrypted_senders": [{"id": r[0], "count": r[1]} for r in encrypted_senders],
        "encrypted_links": [{"from": r[0], "to": r[1], "count": r[2]} for r in encrypted_links],
        "node_positions": positions_map,
        "destinations": {"broadcast": broadcast_cnt, "private": private_cnt},
        "top_types": [{"type": r[0], "count": r[1]} for r in top_types],
        "portnum_types": [r[0] for r in portnum_types],
    }

def get_per_node_analytics(node_id: str, hours: float = 168.0,
                           hide_broadcast: bool = False, no_mqtt: bool = True) -> dict:
    """Return aggregated packet analytics for a specific node over the last `hours` hours."""
    if not _conn:
        return {}

    import time
    start_ts = time.time() - (hours * 3600.0)
    hb_and = "AND to_id NOT IN ('broadcast','ffffffff')" if hide_broadcast else ""
    mq_and = "AND via_mqtt = 0" if no_mqtt else ""

    with _lock:
        # Broadcast count with adaptive bucket size
        hourly, bucket_label = _build_hourly(
            _conn, start_ts, hours, f"AND from_id = ? {mq_and}", hb_and,
            [start_ts, node_id]
        )

        # Top receivers from this node
        top_receivers_rows = _conn.execute(
            """SELECT to_id, COUNT(*) as cnt FROM packets
               WHERE ts > ? AND from_id = ? AND to_id NOT IN ('?', 'broadcast', 'ffffffff')
               GROUP BY to_id ORDER BY cnt DESC LIMIT 1000""",
            (start_ts, node_id)
        ).fetchall()
        top_receivers = [{"id": r[0], "count": r[1]} for r in top_receivers_rows]

        # Top senders to this node
        top_senders_rows = _conn.execute(
            """SELECT from_id, COUNT(*) as cnt FROM packets
               WHERE ts > ? AND to_id = ? AND from_id != '?'
               GROUP BY from_id ORDER BY cnt DESC LIMIT 1000""",
            (start_ts, node_id)
        ).fetchall()
        top_senders = [{"id": r[0], "count": r[1]} for r in top_senders_rows]

        # Daily activity
        daily_rows = _conn.execute(
            """SELECT strftime('%Y-%m-%d', datetime(ts, 'unixepoch', 'localtime')) as day, COUNT(*)
               FROM packets WHERE ts > ? AND from_id = ? GROUP BY day ORDER BY day""",
            (start_ts, node_id)
        ).fetchall()
        daily = [{"label": r[0], "value": r[1]} for r in daily_rows]

        # Text-only receivers (P2P conversations)
        top_receivers_text_rows = _conn.execute(
            """SELECT to_id, COUNT(*) as cnt FROM packets
               WHERE ts > ? AND from_id = ? AND to_id NOT IN ('?', 'broadcast', 'ffffffff')
               AND portnum = 'TEXT_MESSAGE_APP'
               GROUP BY to_id ORDER BY cnt DESC LIMIT 1000""",
            (start_ts, node_id)
        ).fetchall()
        top_receivers_text = [{"id": r[0], "count": r[1]} for r in top_receivers_text_rows]

        # Text-only senders (P2P conversations)
        top_senders_text_rows = _conn.execute(
            """SELECT from_id, COUNT(*) as cnt FROM packets
               WHERE ts > ? AND to_id = ? AND from_id != '?' AND portnum = 'TEXT_MESSAGE_APP'
               GROUP BY from_id ORDER BY cnt DESC LIMIT 1000""",
            (start_ts, node_id)
        ).fetchall()
        top_senders_text = [{"id": r[0], "count": r[1]} for r in top_senders_text_rows]

        # Destinations summary
        dest_stats = _conn.execute(
            """SELECT
               SUM(CASE WHEN to_id IN ('broadcast', 'ffffffff') THEN 1 ELSE 0 END) as broadcast_cnt,
               SUM(CASE WHEN to_id NOT IN ('broadcast', 'ffffffff') AND to_id != '?' THEN 1 ELSE 0 END) as private_cnt
               FROM packets WHERE ts > ? AND from_id = ?""",
            (start_ts, node_id)
        ).fetchone()
        broadcast_cnt = dest_stats[0] or 0
        private_cnt = dest_stats[1] or 0

        return {
            "hourly": hourly,
            "bucket_label": bucket_label,
            "top_receivers": top_receivers,
            "top_senders": top_senders,
            "top_receivers_text": top_receivers_text,
            "top_senders_text": top_senders_text,
            "daily": daily,
            "destinations": {"broadcast": broadcast_cnt, "private": private_cnt}
        }
