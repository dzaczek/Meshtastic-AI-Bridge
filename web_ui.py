"""
web_ui.py - Password-protected web dashboard for Meshtastic AI Bridge.

Features:
  - Session-based auth with optional "Remember me" (30-day cookie)
  - Chat tab: messages by channel/time, send form
  - Nodes tab: node cards with hops, SNR, battery, GPS
  - Map tab: Leaflet.js interactive map
  - Packets tab: live raw packet feed + stats

Environment variables:
  WEB_UI_PASSWORD    - required; server will NOT start if empty
  WEB_UI_USERNAME    - default: admin
  WEB_UI_PORT        - default: 8080
  WEB_UI_SECRET_KEY  - Flask session secret (auto-generated if missing)
"""

import logging
import os
import threading
import time
from collections import deque
from datetime import datetime, timedelta
from functools import wraps

logger = logging.getLogger("web_ui")

try:
    import node_db as _node_db
    _HAS_NODE_DB = True
except ImportError:
    _HAS_NODE_DB = False

try:
    from flask import (
        Flask, jsonify, redirect, render_template,
        request, session, url_for,
    )
    _HAS_FLASK = True
except ImportError:
    _HAS_FLASK = False
    logger.warning("web_ui: Flask not installed — web interface disabled")


# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------

_messages: deque = deque(maxlen=500)
_packets:  deque = deque(maxlen=1000)
_status: dict = {
    "connected": False,
    "node_id": None,
    "ai_service": "openai",
    "uptime_start": time.time(),
    "messages_received": 0,
    "ai_responses": 0,
    "reconnecting": False,
    "last_error": None,
}
_lock = threading.Lock()
_send_callback  = None   # (text, channel) -> (bool, str)
_meshtastic_handler = None
_bot_name: str = "AI"


def set_bot_name(name: str) -> None:
    global _bot_name
    _bot_name = name.strip() if name else "AI"


def get_bot_name() -> str:
    return _bot_name


# ---------------------------------------------------------------------------
# Public API (called from main_app)
# ---------------------------------------------------------------------------

def add_message(text: str, sender: str, channel: int,
                msg_type: str = "rx", timestamp: float | None = None,
                sender_id: str | None = None):
    ts = timestamp or time.time()
    with _lock:
        _messages.append({
            "id":        int(ts * 1000),
            "text":      text,
            "sender":    sender,
            "sender_id": sender_id or "",
            "channel":   channel,
            "type":      msg_type,
            "timestamp": ts,
            "ts_str":    datetime.fromtimestamp(ts).strftime("%H:%M:%S"),
        })
        if msg_type == "rx":
            _status["messages_received"] += 1
        elif msg_type == "ai":
            _status["ai_responses"] += 1


def update_status(**kwargs):
    with _lock:
        _status.update(kwargs)


def set_send_callback(callback):
    global _send_callback
    _send_callback = callback


def set_meshtastic_handler(handler):
    global _meshtastic_handler
    _meshtastic_handler = handler


def on_packet(packet, interface):
    """Raw packet callback — register this with MeshtasticHandler."""
    try:
        pkt = _parse_packet(packet, interface)
        with _lock:
            _packets.append(pkt)
        if _HAS_NODE_DB:
            _persist_packet(packet, pkt, interface)
    except Exception:
        pass


def _persist_packet(raw: dict, parsed: dict, interface) -> None:
    """Persist packet data to node_db."""
    node_id = parsed.get("from_id", "")
    if not node_id or node_id == "?":
        return

    decoded  = raw.get("decoded") or {}
    portnum  = decoded.get("portnum", "")
    via_mqtt = bool(parsed.get("via_mqtt", False))
    from_num = raw.get("from")

    # Resolve names: NODEINFO gives authoritative names; otherwise use interface cache
    long_name = short_name = hw_model = role = ""
    if portnum == "NODEINFO_APP":
        user = decoded.get("user") or {}
        long_name  = user.get("longName", "")
        short_name = user.get("shortName", "")
        hw_model   = user.get("hwModel", "")
        role       = user.get("role", "")
    elif interface and hasattr(interface, "nodes"):
        for nd in (interface.nodes or {}).values():
            if nd.get("num") == from_num:
                u = nd.get("user", {})
                long_name  = u.get("longName", "")
                short_name = u.get("shortName", "")
                hw_model   = u.get("hwModel", "")
                role       = u.get("role", "")
                break

    _node_db.upsert_node(
        node_id, num=from_num,
        long_name=long_name, short_name=short_name,
        hw_model=hw_model, role=role, via_mqtt=via_mqtt,
    )

    # Signal quality
    snr  = parsed.get("snr")
    rssi = parsed.get("rssi")
    hop_start = parsed.get("hop_start")
    hop_limit = parsed.get("hop_limit")
    hops_away = (hop_start - hop_limit) if (hop_start is not None and hop_limit is not None) else None
    _node_db.add_signal(node_id, snr=snr, rssi=rssi, hops_away=hops_away, via_mqtt=via_mqtt)

    # Position
    if portnum == "POSITION_APP":
        pos   = decoded.get("position") or {}
        lat_i = pos.get("latitudeI", 0)
        lon_i = pos.get("longitudeI", 0)
        lat   = lat_i / 1e7 if lat_i else None
        lon   = lon_i / 1e7 if lon_i else None
        if lat and lon:
            _node_db.add_position(
                node_id, lat=lat, lon=lon,
                alt=pos.get("altitude"),
                sats=pos.get("satsInView"),
            )

    # Telemetry
    elif portnum == "TELEMETRY_APP":
        tel = decoded.get("telemetry") or {}
        dev = tel.get("deviceMetrics") or {}
        env = tel.get("environmentMetrics") or {}
        _node_db.add_telemetry(
            node_id,
            battery=dev.get("batteryLevel"),
            voltage=dev.get("voltage"),
            uptime_s=dev.get("uptimeSeconds"),
            ch_util=dev.get("channelUtilization"),
            air_util=dev.get("airUtilTx"),
            temperature=env.get("temperature"),
            humidity=env.get("humidity"),
            pressure=env.get("barometricPressure"),
        )

    # Text message
    elif portnum == "TEXT_MESSAGE_APP":
        text = decoded.get("text", "")
        if text:
            _node_db.add_message(
                node_id, text=text, direction="rx",
                channel=raw.get("channel", 0),
            )


# ---------------------------------------------------------------------------
# Packet parsing
# ---------------------------------------------------------------------------

def _packet_summary(portnum: str, decoded: dict) -> str:
    if portnum == "TEXT_MESSAGE_APP":
        t = decoded.get("text", "")
        return t[:70] + ("…" if len(t) > 70 else "")
    if portnum == "POSITION_APP":
        pos = decoded.get("position", {})
        lat_i = pos.get("latitudeI", 0)
        lon_i = pos.get("longitudeI", 0)
        lat = lat_i / 1e7 if lat_i else 0.0
        lon = lon_i / 1e7 if lon_i else 0.0
        alt = pos.get("altitude")
        return f"{lat:.4f},{lon:.4f}" + (f" @{alt}m" if alt else "")
    if portnum == "TELEMETRY_APP":
        dev = (decoded.get("telemetry") or {}).get("deviceMetrics") or {}
        env = (decoded.get("telemetry") or {}).get("environmentMetrics") or {}
        parts = []
        if dev.get("batteryLevel") is not None:
            parts.append(f"bat:{dev['batteryLevel']}%")
        if dev.get("channelUtilization") is not None:
            parts.append(f"util:{dev['channelUtilization']:.1f}%")
        if env.get("temperature") is not None:
            parts.append(f"{env['temperature']:.1f}°C")
        return " ".join(parts) or "telemetry"
    if portnum == "NODEINFO_APP":
        u = decoded.get("user", {})
        return f"{u.get('longName','?')} ({u.get('shortName','?')})"
    if portnum == "ROUTING_APP":
        return "routing / ack"
    if portnum == "TRACEROUTE_APP":
        return "traceroute"
    if portnum == "ADMIN_APP":
        return "admin packet"
    if portnum == "RANGE_TEST_APP":
        return decoded.get("payload", b"").decode("utf-8", errors="replace")[:40]
    return portnum.replace("_APP", "").replace("_", " ").lower()


_BROADCAST_HEX = "ffffffff"


def _sanitize(obj):
    """Recursively make obj JSON-safe (bytes → hex, unknowns → str)."""
    if isinstance(obj, bytes):
        return obj.hex()
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    try:
        import json; json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return str(obj)


def _parse_packet(packet: dict, interface) -> dict:
    decoded = packet.get("decoded") or {}
    portnum = decoded.get("portnum", "UNKNOWN_APP")

    from_num = packet.get("from")
    to_num   = packet.get("to")

    from_id = f"{from_num:x}" if from_num else "?"
    to_id   = f"{to_num:x}"   if to_num   else "broadcast"
    if to_id in (_BROADCAST_HEX, "4294967295"):
        to_id = "broadcast"

    # Resolve name from node cache
    from_name = from_id
    if interface and hasattr(interface, "nodes"):
        for nd in (interface.nodes or {}).values():
            if nd.get("num") == from_num:
                u = nd.get("user", {})
                from_name = u.get("shortName") or u.get("longName") or from_id
                break

    snr  = packet.get("rxSnr")  or packet.get("snr")
    rssi = packet.get("rxRssi") or packet.get("rssi")

    type_label = portnum.replace("_APP", "").replace("_", " ")

    ts = time.time()
    return {
        "ts":         ts,
        "ts_str":     datetime.fromtimestamp(ts).strftime("%H:%M:%S"),
        "from_id":    from_id,
        "from_name":  from_name,
        "to_id":      to_id,
        "channel":    packet.get("channel", 0),
        "portnum":    type_label,
        "portnum_raw": portnum,
        "hop_limit":  packet.get("hopLimit"),
        "hop_start":  packet.get("hopStart"),
        "snr":        round(float(snr), 1)  if snr  is not None else None,
        "rssi":       int(rssi)             if rssi is not None else None,
        "via_mqtt":   packet.get("viaMqtt", False),
        "want_ack":   packet.get("wantAck", False),
        "summary":    _packet_summary(portnum, decoded),
        "decoded_raw": _sanitize(decoded),
    }


# ---------------------------------------------------------------------------
# Node / channel helpers
# ---------------------------------------------------------------------------

def _build_nodes_list(handler) -> list:
    if not handler or not handler.interface:
        return []
    raw = getattr(handler.interface, "nodes", None) or {}
    my_num = handler.node_id
    now    = time.time()
    result = []

    for nd in raw.values():
        user     = nd.get("user", {})
        num      = nd.get("num")
        node_id  = f"{num:x}" if num else user.get("id", "").lstrip("!")

        is_mqtt  = nd.get("viaMqtt", False)
        hops     = nd.get("hopsAway")
        if not is_mqtt and hops == -1:
            is_mqtt = True

        last = nd.get("lastHeard", 0)
        age  = int(now - last) if last else None

        pos  = nd.get("position") or {}
        lat  = pos.get("latitude")
        lon  = pos.get("longitude")
        if lat is not None: lat = float(lat)
        if lon is not None: lon = float(lon)

        metrics = nd.get("deviceMetrics") or {}
        battery = nd.get("batteryLevel") or metrics.get("batteryLevel")
        voltage = metrics.get("voltage")
        uptime  = nd.get("uptimeSeconds") or metrics.get("uptimeSeconds")

        result.append({
            "id":        node_id,
            "num":       num,
            "long_name": user.get("longName", f"Node-{node_id}"),
            "short_name":user.get("shortName", "???"),
            "hw_model":  user.get("hwModel", ""),
            "role":      user.get("role", ""),
            "hops_away": hops,
            "is_direct": hops == 0,
            "via_mqtt":  is_mqtt,
            "last_heard":last,
            "age_s":     age,
            "is_online": bool(last and age is not None and age < 3600),
            "rssi":      nd.get("rssi") or nd.get("lastPacketRssi"),
            "snr":       nd.get("snr")  or nd.get("lastPacketSnr"),
            "battery":   battery,
            "voltage":   round(float(voltage), 2) if voltage else None,
            "uptime_s":  uptime,
            "lat":       lat,
            "lon":       lon,
            "altitude":  pos.get("altitude"),
            "is_mine":   num == my_num,
            "is_favorite": nd.get("isFavorite", False),
        })

    result.sort(key=lambda n: (
        n["via_mqtt"],
        n["hops_away"] if n["hops_away"] is not None else 98,
        -(n["last_heard"] or 0),
    ))
    return result


def _build_channels_list(handler) -> list:
    if not handler or not handler.interface:
        return []
    try:
        return handler.list_channels()
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

if _HAS_FLASK:
    app = Flask(__name__, template_folder="templates")
    app.secret_key = os.environ.get("WEB_UI_SECRET_KEY") or os.urandom(32)
    app.permanent_session_lifetime = timedelta(days=30)

    WEB_UI_PASSWORD = os.environ.get("WEB_UI_PASSWORD", "")
    WEB_UI_USERNAME = os.environ.get("WEB_UI_USERNAME", "admin")

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def login_required(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not session.get("logged_in"):
                return redirect(url_for("login"))
            return f(*args, **kwargs)
        return decorated

    @app.route("/login", methods=["GET", "POST"])
    def login():
        error = None
        if request.method == "POST":
            u = request.form.get("username", "")
            p = request.form.get("password", "")
            remember = request.form.get("remember") == "on"
            if u == WEB_UI_USERNAME and p == WEB_UI_PASSWORD:
                session.permanent = remember
                session["logged_in"] = True
                return redirect(url_for("index"))
            error = "Invalid credentials"
        return render_template("login.html", error=error)

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/")
    @login_required
    def index():
        return render_template("index.html")

    @app.route("/health")
    def health():
        with _lock:
            ok = _status.get("connected", False)
        return jsonify({"ok": True, "connected": ok}), 200

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    @app.route("/api/messages")
    @login_required
    def api_messages():
        since = float(request.args.get("since", 0))
        with _lock:
            msgs = [m for m in _messages if m["timestamp"] > since]
        return jsonify({"messages": msgs, "server_time": time.time()})

    @app.route("/api/status")
    @login_required
    def api_status():
        with _lock:
            st = dict(_status)
        elapsed = int(time.time() - st.pop("uptime_start"))
        h, r = divmod(elapsed, 3600)
        m, s = divmod(r, 60)
        st["uptime_s"]   = elapsed
        st["uptime_str"] = f"{h:02d}:{m:02d}:{s:02d}"
        st["bot_name"]   = _bot_name
        return jsonify(st)

    @app.route("/api/send", methods=["POST"])
    @login_required
    def api_send():
        data    = request.get_json(silent=True) or {}
        text    = (data.get("text") or "").strip()
        channel = int(data.get("channel", 0))
        if not text:
            return jsonify({"ok": False, "error": "Empty message"}), 400
        if not _send_callback:
            return jsonify({"ok": False, "error": "Send callback not configured"}), 503
        try:
            ok, reason = _send_callback(text, channel)
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        if ok:
            add_message(text, "WebUI", channel, "tx")
        return jsonify({"ok": ok, "reason": reason})

    @app.route("/api/nodes")
    @login_required
    def api_nodes():
        live = _build_nodes_list(_meshtastic_handler)
        if not _HAS_NODE_DB:
            return jsonify({"nodes": live, "ts": time.time()})
        live_ids = {n["id"] for n in live}
        now = time.time()
        merged = list(live)
        for db_n in _node_db.get_all_nodes():
            if db_n["id"] in live_ids:
                continue
            age = int(now - db_n["last_seen"]) if db_n.get("last_seen") else None
            merged.append({
                "id":         db_n["id"],
                "num":        db_n.get("num"),
                "long_name":  db_n.get("long_name") or f"Node-{db_n['id']}",
                "short_name": db_n.get("short_name") or "???",
                "hw_model":   db_n.get("hw_model", ""),
                "role":       db_n.get("role", ""),
                "hops_away":  None,
                "is_direct":  False,
                "via_mqtt":   bool(db_n.get("via_mqtt", 0)),
                "last_heard": db_n.get("last_seen"),
                "age_s":      age,
                "is_online":  False,
                "rssi":       None,
                "snr":        None,
                "battery":    None,
                "voltage":    None,
                "uptime_s":   None,
                "lat":        None,
                "lon":        None,
                "altitude":   None,
                "is_mine":    False,
                "is_favorite": False,
                "from_db":    True,
            })
        return jsonify({"nodes": merged, "ts": now})

    @app.route("/api/channels")
    @login_required
    def api_channels():
        return jsonify({"channels": _build_channels_list(_meshtastic_handler)})

    @app.route("/api/packets")
    @login_required
    def api_packets():
        since = float(request.args.get("since", 0))
        with _lock:
            pkts = [p for p in _packets if p["ts"] > since]
        return jsonify({"packets": pkts, "server_time": time.time()})

    @app.route("/api/packet_stats")
    @login_required
    def api_packet_stats():
        now = time.time()
        with _lock:
            total = len(_packets)
            by_type: dict = {}
            by_ch:   dict = {}
            last_min  = 0
            last_5min = 0
            for p in _packets:
                t = p["portnum"]
                by_type[t] = by_type.get(t, 0) + 1
                ch = str(p.get("channel", 0))
                by_ch[ch] = by_ch.get(ch, 0) + 1
                age = now - p["ts"]
                if age < 60:   last_min  += 1
                if age < 300:  last_5min += 1

        # Sort by count
        by_type = dict(sorted(by_type.items(), key=lambda x: -x[1]))
        return jsonify({
            "total":          total,
            "by_type":        by_type,
            "by_channel":     by_ch,
            "last_min":       last_min,
            "last_5min":      last_5min,
        })

    @app.route("/api/clear_error", methods=["POST"])
    @login_required
    def api_clear_error():
        with _lock:
            _status["last_error"] = None
        return jsonify({"ok": True})

    # ------------------------------------------------------------------
    # Per-node history (node_db)
    # ------------------------------------------------------------------

    @app.route("/api/node/<node_id>")
    @login_required
    def api_node(node_id):
        if not _HAS_NODE_DB:
            return jsonify({"error": "node_db not available"}), 503
        node  = _node_db.get_node(node_id)
        stats = _node_db.get_node_stats(node_id)
        return jsonify({"node": node, "stats": stats})

    @app.route("/api/node/<node_id>/signal")
    @login_required
    def api_node_signal(node_id):
        if not _HAS_NODE_DB:
            return jsonify({"signal": []})
        limit = min(int(request.args.get("limit", 300)), 1000)
        return jsonify({"signal": _node_db.get_signal_history(node_id, limit=limit)})

    @app.route("/api/node/<node_id>/positions")
    @login_required
    def api_node_positions(node_id):
        if not _HAS_NODE_DB:
            return jsonify({"positions": []})
        limit = min(int(request.args.get("limit", 500)), 2000)
        return jsonify({"positions": _node_db.get_position_history(node_id, limit=limit)})

    @app.route("/api/node/<node_id>/telemetry")
    @login_required
    def api_node_telemetry(node_id):
        if not _HAS_NODE_DB:
            return jsonify({"telemetry": []})
        limit = min(int(request.args.get("limit", 300)), 1000)
        return jsonify({"telemetry": _node_db.get_telemetry_history(node_id, limit=limit)})

    @app.route("/api/node/<node_id>/messages")
    @login_required
    def api_node_messages(node_id):
        if not _HAS_NODE_DB:
            return jsonify({"messages": []})
        limit = min(int(request.args.get("limit", 200)), 500)
        return jsonify({"messages": _node_db.get_message_history(node_id, limit=limit)})

    # ------------------------------------------------------------------
    # Device configuration
    # ------------------------------------------------------------------

    @app.route("/api/config")
    @login_required
    def api_config():
        if not _meshtastic_handler:
            return jsonify({"_error": "Not connected"}), 503
        return jsonify(_meshtastic_handler.get_device_config())

    @app.route("/api/config/debug")
    @login_required
    def api_config_debug():
        if not _meshtastic_handler:
            return jsonify({"error": "Not connected"}), 503
        return jsonify(_meshtastic_handler._raw_config_debug())

    @app.route("/api/config/<section>", methods=["POST"])
    @login_required
    def api_config_save(section):
        if not _meshtastic_handler:
            return jsonify({"ok": False, "error": "Not connected"}), 503
        data = request.get_json(silent=True) or {}
        ok, msg = _meshtastic_handler.set_device_config(section, data)
        return jsonify({"ok": ok, "message": msg})


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------

_server_thread: threading.Thread | None = None


def start_in_background(host: str = "0.0.0.0", port: int = 8080) -> threading.Thread | None:
    if not _HAS_FLASK:
        logger.error("web_ui: Flask not available")
        return None
    password = os.environ.get("WEB_UI_PASSWORD", "")
    if not password:
        logger.warning("web_ui: WEB_UI_PASSWORD not set — server will NOT start")
        add_message("Web UI disabled: WEB_UI_PASSWORD not set", "system", -1, "system")
        return None

    global _server_thread

    def _run():
        logger.info(f"web_ui: listening on http://{host}:{port}")
        add_message(f"Web UI available on port {port}", "system", -1, "system")
        try:
            from werkzeug.serving import run_simple
            run_simple(host, port, app, threaded=True, use_reloader=False)
        except Exception:
            app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)

    _server_thread = threading.Thread(target=_run, daemon=True, name="WebUI")
    _server_thread.start()
    return _server_thread
