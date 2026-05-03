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

import json
import base64
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

try:
    from webauthn import (
        generate_registration_options,
        verify_registration_response,
        generate_authentication_options,
        verify_authentication_response,
        options_to_json,
    )
    from webauthn.helpers.structs import (
        AuthenticatorSelectionCriteria,
        PublicKeyCredentialDescriptor,
        RegistrationCredential,
        AuthenticationCredential,
        ResidentKeyRequirement,
        UserVerificationRequirement,
    )
    _HAS_WEBAUTHN = True
except ImportError:
    _HAS_WEBAUTHN = False


# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------

_messages: deque = deque(maxlen=500)
_packets:  deque = deque(maxlen=1000)

_CHAT_HISTORY_PATH = os.path.join("data", "chat_history.json")
_WEBAUTHN_CREDENTIALS_PATH = os.path.join("data", "webauthn_credentials.json")
_LAYOUTS_PATH = os.path.join("data", "layouts.json")
_UI_SETTINGS_PATH = os.path.join("data", "ui_settings.json")
_save_pending = False


def _load_ui_settings() -> None:
    global _status
    try:
        if os.path.exists(_UI_SETTINGS_PATH):
            with open(_UI_SETTINGS_PATH) as f:
                saved = json.load(f)
            _status["bot_private_replies"]  = bool(saved.get("bot_private_replies", False))
            _status["ai_enabled"]           = bool(saved.get("ai_enabled", True))
            _status["sys_packets_to_chat"]  = bool(saved.get("sys_packets_to_chat", False))
    except Exception as e:
        logger.warning(f"ui_settings: could not load: {e}")


def _save_ui_settings() -> None:
    try:
        os.makedirs(os.path.dirname(_UI_SETTINGS_PATH), exist_ok=True)
        with open(_UI_SETTINGS_PATH, "w") as f:
            json.dump({
                "bot_private_replies":  _status.get("bot_private_replies", False),
                "ai_enabled":           _status.get("ai_enabled", True),
                "sys_packets_to_chat":  _status.get("sys_packets_to_chat", False),
            }, f)
    except Exception as e:
        logger.warning(f"ui_settings: could not save: {e}")


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _load_webauthn_credentials() -> list[dict]:
    if not os.path.exists(_WEBAUTHN_CREDENTIALS_PATH):
        return []
    try:
        with open(_WEBAUTHN_CREDENTIALS_PATH, "r", encoding="utf-8") as f:
            creds = json.load(f)
        return creds if isinstance(creds, list) else []
    except Exception as e:
        logger.warning(f"webauthn: could not load credentials: {e}")
        return []


def _save_webauthn_credentials(creds: list[dict]) -> None:
    try:
        os.makedirs(os.path.dirname(_WEBAUTHN_CREDENTIALS_PATH), exist_ok=True)
        with open(_WEBAUTHN_CREDENTIALS_PATH, "w", encoding="utf-8") as f:
            json.dump(creds, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"webauthn: could not save credentials: {e}")


def _load_chat_history() -> None:
    """Load persisted messages from disk into _messages on startup."""
    try:
        if not os.path.exists(_CHAT_HISTORY_PATH):
            return
        with open(_CHAT_HISTORY_PATH, "r", encoding="utf-8") as f:
            saved = json.load(f)
        count = 0
        for msg in saved[-500:]:
            if isinstance(msg, dict) and "text" in msg and "timestamp" in msg:
                _messages.append(msg)
                count += 1
        logger.info(f"chat_history: loaded {count} messages from {_CHAT_HISTORY_PATH}")
    except Exception as e:
        logger.warning(f"chat_history: could not load: {e}")


def _save_chat_history() -> None:
    """Persist current _messages to disk."""
    global _save_pending
    _save_pending = False
    try:
        os.makedirs(os.path.dirname(_CHAT_HISTORY_PATH), exist_ok=True)
        with _lock:
            msgs = list(_messages)
        with open(_CHAT_HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(msgs, f, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"chat_history: could not save: {e}")


def _schedule_save() -> None:
    """Debounced save — waits 10s after last message before writing."""
    global _save_pending
    if _save_pending:
        return
    _save_pending = True
    t = threading.Timer(10.0, _save_chat_history)
    t.daemon = True
    t.start()


_status: dict = {
    "connected": False,
    "node_id": None,
    "ai_service": "openai",
    "uptime_start": time.time(),
    "messages_received": 0,
    "ai_responses": 0,
    "reconnecting": False,
    "last_error": None,
    "ai_enabled": True,
    "bot_private_replies": False,
    "sys_packets_to_chat": False,
}

# Load persisted messages and UI settings immediately at module import
_load_chat_history()
_load_ui_settings()


def is_ai_enabled() -> bool:
    return _status.get("ai_enabled", True)


def is_bot_private_replies() -> bool:
    return _status.get("bot_private_replies", False)


def is_sys_packets_to_chat() -> bool:
    return _status.get("sys_packets_to_chat", False)
_lock = threading.Lock()
_send_callback  = None
_meshtastic_handler = None
_bot_name: str = "AI"
_pending_acks: dict = {}       # mesh_packet_id(int) → web_message_id(int)
_traceroutes: deque = deque(maxlen=200)  # parsed traceroute records


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
                sender_id: str | None = None, ack: str = "none",
                destination_id: str | None = None):
    channel = 0 if channel is None else channel
    ts = timestamp or time.time()
    web_id = int(ts * 1000)
    with _lock:
        _messages.append({
            "id":             web_id,
            "text":           text,
            "sender":         sender,
            "sender_id":      sender_id or "",
            "destination_id": destination_id or "",
            "channel":        channel,
            "type":           msg_type,
            "ack":            ack,        # 'none'|'pending'|'ok'|'fail'
            "timestamp":      ts,
            "ts_str":         datetime.fromtimestamp(ts).strftime("%H:%M:%S"),
        })
        if msg_type == "rx":
            _status["messages_received"] += 1
        elif msg_type == "ai":
            _status["ai_responses"] += 1
    _schedule_save()
    return web_id


def update_status(**kwargs):
    with _lock:
        _status.update(kwargs)


def set_send_callback(callback):
    global _send_callback
    _send_callback = callback


def _load_packet_history() -> None:
    """Pre-populate _packets deque with recent history from SQLite after node_db is ready."""
    if not _HAS_NODE_DB or not _node_db.is_initialized():
        return
    try:
        import json as _json
        rows = _node_db._conn.execute(
            "SELECT packet_json FROM packets ORDER BY ts DESC LIMIT 500"
        ).fetchall()
        loaded = []
        for r in rows:
            try:
                pkt = _json.loads(r[0])
                if "ts_str" not in pkt and "ts" in pkt:
                    pkt["ts_str"] = datetime.fromtimestamp(pkt["ts"]).strftime("%H:%M:%S")
                loaded.append(pkt)
            except Exception:
                pass
        with _lock:
            for pkt in reversed(loaded):   # oldest first → correct deque order
                _packets.append(pkt)
        logger.info(f"packet_history: loaded {len(loaded)} packets from SQLite")
    except Exception as e:
        logger.warning(f"packet_history: could not load: {e}")


def set_meshtastic_handler(handler):
    global _meshtastic_handler
    _meshtastic_handler = handler
    _load_packet_history()


_SYS_PKT_ICONS = {
    "NODEINFO_APP":   "📡",
    "TELEMETRY_APP":  "📊",
    "POSITION_APP":   "📍",
    "ROUTING_APP":    "🔀",
    "TRACEROUTE_APP": "🔍",
    "RANGE_TEST_APP": "📶",
    "ADMIN_APP":      "⚙",
}


def on_packet(packet, interface):
    """Raw packet callback — register this with MeshtasticHandler."""
    try:
        pkt = _parse_packet(packet, interface)
        with _lock:
            _packets.append(pkt)
        if _HAS_NODE_DB:
            _persist_packet(packet, pkt, interface)
            _node_db.add_packet_record(pkt)
        _handle_ack(packet)
        tr = _parse_traceroute(packet, interface)
        if tr:
            with _lock:
                _traceroutes.append(tr)
            if _HAS_NODE_DB:
                try:
                    _node_db.add_traceroute(
                        from_id=tr['from_id'],
                        to_id=tr['to_id'],
                        hops=tr['hops'],
                        route=tr['route'],
                        snr_towards=tr['snr_towards'],
                        channel=tr.get('channel', 0),
                        ts=tr['ts'],
                    )
                except Exception:
                    pass

        # Generate system chat message when sys_packets_to_chat is enabled
        if _status.get("sys_packets_to_chat", False):
            portnum = pkt.get("portnum", "")
            if portnum in _SYS_PKT_ICONS and portnum != "TEXT_MESSAGE_APP":
                icon   = _SYS_PKT_ICONS[portnum]
                sender = pkt.get("from_name") or pkt.get("from_id") or "?"
                summary = pkt.get("summary") or portnum.replace("_APP", "").lower()
                via    = " [MQTT]" if pkt.get("via_mqtt") else ""
                text   = f"{icon} {sender}{via}: {summary}"
                add_message(text, "mesh", -1, "system",
                            timestamp=pkt.get("ts"),
                            sender_id=pkt.get("from_id") or "")
    except Exception:
        pass


def _node_name(node_id_hex: str, interface) -> str:
    if not interface or not hasattr(interface, 'nodes'):
        return node_id_hex
    for nd in (interface.nodes or {}).values():
        num = nd.get('num')
        if num and f"{num:x}" == node_id_hex:
            u = nd.get('user', {})
            return u.get('shortName') or u.get('longName') or node_id_hex
    return node_id_hex


def _node_pos(node_id_hex: str, interface):
    """Return (lat, lon) for a node — tries interface.nodes then node_db."""
    # 1. Live interface node cache
    if interface and hasattr(interface, 'nodes'):
        for nd in (interface.nodes or {}).values():
            num = nd.get('num')
            if num and f"{num:x}" == node_id_hex:
                pos = nd.get('position') or {}
                # Coordinates may be stored as float or as integer × 1e-7
                lat = pos.get('latitude') or (pos.get('latitudeI', 0) / 1e7 or None)
                lon = pos.get('longitude') or (pos.get('longitudeI', 0) / 1e7 or None)
                if lat and lon:
                    return float(lat), float(lon)
    # 2. node_db — last known GPS position
    if _HAS_NODE_DB:
        try:
            rows = _node_db.get_position_history(node_id_hex, limit=1)
            if rows:
                r = rows[0]
                if r.get('lat') and r.get('lon'):
                    return float(r['lat']), float(r['lon'])
        except Exception:
            pass
    return None


def _parse_traceroute(packet: dict, interface) -> dict | None:
    decoded = packet.get('decoded') or {}
    if decoded.get('portnum') != 'TRACEROUTE_APP':
        return None
    tr       = decoded.get('traceroute') or {}
    from_num = packet.get('from')
    to_num   = packet.get('to')
    from_id  = f"{from_num:x}" if from_num else "?"
    to_id    = f"{to_num:x}"   if to_num   else "?"
    inter_ids = [f"{n:x}" for n in (tr.get('route') or [])]
    full_ids  = [from_id] + inter_ids + [to_id]
    nodes = []
    for nid in full_ids:
        pos = _node_pos(nid, interface)
        nodes.append({
            'id':   nid,
            'name': _node_name(nid, interface),
            'lat':  pos[0] if pos else None,
            'lon':  pos[1] if pos else None,
        })
    ts = time.time()
    return {
        'ts':          ts,
        'ts_str':      datetime.fromtimestamp(ts).strftime("%H:%M:%S"),
        'from_id':     from_id,
        'from_name':   _node_name(from_id, interface),
        'to_id':       to_id,
        'to_name':     _node_name(to_id, interface),
        'hops':        len(inter_ids),
        'route':       nodes,
        'snr_towards': tr.get('snr_towards') or tr.get('snrTowards') or [],
        'snr_back':    tr.get('snr_back')    or tr.get('snrBack')    or [],
        'channel':     packet.get('channel', 0),
        'rssi':        packet.get('rxRssi') or packet.get('rssi'),
        'snr':         packet.get('rxSnr')  or packet.get('snr'),
    }


def update_message_ack(web_id: int, ack: str) -> None:
    with _lock:
        for msg in _messages:
            if msg.get("id") == web_id:
                msg["ack"] = ack
                break


def _handle_ack(packet: dict) -> None:
    decoded = packet.get("decoded") or {}
    if decoded.get("portnum") != "ROUTING_APP":
        return
    request_id = decoded.get("request_id") or decoded.get("requestId")
    if not request_id:
        return
    routing = decoded.get("routing") or {}
    error = routing.get("error_reason") or routing.get("errorReason") or 0
    ack_status = "ok" if error == 0 else "fail"
    with _lock:
        web_id = _pending_acks.pop(int(request_id), None)
        if web_id is not None:
            for msg in _messages:
                if msg.get("id") == web_id:
                    msg["ack"] = ack_status
                    break


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
    raw_decoded = packet.get("decoded")
    # If decoded is absent or empty the packet is encrypted with a key we don't have
    encrypted = not raw_decoded
    decoded  = raw_decoded or {}
    portnum  = decoded.get("portnum", "UNKNOWN_APP")
    if isinstance(portnum, int):
        # Some library versions return the enum as an integer
        portnum = f"PORT_{portnum}"

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

    if encrypted:
        type_label = "ENCRYPTED"
        summary    = f"ch{packet.get('channel',0)} · key mismatch — check channel PSK"
    else:
        type_label = portnum.replace("_APP", "").replace("_", " ")
        summary    = _packet_summary(portnum, decoded)

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
        "encrypted":  encrypted,
        "hop_limit":  packet.get("hopLimit"),
        "hop_start":  packet.get("hopStart"),
        "snr":        round(float(snr), 1)  if snr  is not None else None,
        "rssi":       int(rssi)             if rssi is not None else None,
        "via_mqtt":   packet.get("viaMqtt", False),
        "want_ack":   packet.get("wantAck", False),
        "summary":    summary,
        "decoded_raw": _sanitize(decoded),
    }


# ---------------------------------------------------------------------------
# Node / channel helpers
# ---------------------------------------------------------------------------

_LOC_SRC_MAP = {"LOC_UNSET": 0, "LOC_MANUAL": 1, "LOC_INTERNAL": 2, "LOC_EXTERNAL": 3}


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
        # Fall back to integer lat/lon if float version is absent/zero
        if not lat or not lon:
            lat_i = pos.get("latitudeI", 0)
            lon_i = pos.get("longitudeI", 0)
            if lat_i: lat = lat_i / 1e7
            if lon_i: lon = lon_i / 1e7
        loc_src = pos.get("locationSource") or pos.get("location_source") or 0
        # The Meshtastic library may return loc_src as a string enum name
        # (e.g. 'LOC_MANUAL') or as an integer. Map both safely to an int.
        if isinstance(loc_src, str):
            loc_src_int = _LOC_SRC_MAP.get(loc_src, 0)
        else:
            try:
                loc_src_int = int(loc_src)
            except (TypeError, ValueError):
                loc_src_int = 0

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
            "altitude":      pos.get("altitude"),
            "location_source": loc_src_int,
            "is_mine":       num == my_num,
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
# Helpers
# ---------------------------------------------------------------------------

def _fmt_age(s: int) -> str:
    if s < 60:   return f"{s}s ago"
    if s < 3600: return f"{s//60}m ago"
    return f"{s//3600}h ago"


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

if _HAS_FLASK:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.secret_key = os.environ.get("WEB_UI_SECRET_KEY") or os.urandom(32)
    app.permanent_session_lifetime = timedelta(days=30)

    WEB_UI_PASSWORD = os.environ.get("WEB_UI_PASSWORD", "")
    WEB_UI_USERNAME = os.environ.get("WEB_UI_USERNAME", "admin")
    WEB_UI_RP_ID = os.environ.get("WEB_UI_WEBAUTHN_RP_ID", "localhost")
    WEB_UI_RP_NAME = os.environ.get("WEB_UI_WEBAUTHN_RP_NAME", "Meshtastic AI Bridge")
    WEB_UI_ORIGIN = os.environ.get("WEB_UI_WEBAUTHN_ORIGIN", f"http://{WEB_UI_RP_ID}:8080")

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
        return render_template("login.html", error=error, username=WEB_UI_USERNAME)

    @app.route("/api/auth/passkey/register/begin", methods=["POST"])
    @login_required
    def passkey_register_begin():
        if not _HAS_WEBAUTHN:
            return jsonify({"ok": False, "error": "WebAuthn backend not installed"}), 501
        user_handle = WEB_UI_USERNAME.encode("utf-8")
        creds = _load_webauthn_credentials()
        exclude_creds = [PublicKeyCredentialDescriptor(id=_b64url_decode(c["credential_id"])) for c in creds]
        options = generate_registration_options(
            rp_id=WEB_UI_RP_ID,
            rp_name=WEB_UI_RP_NAME,
            user_id=user_handle,
            user_name=WEB_UI_USERNAME,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.PREFERRED,
                user_verification=UserVerificationRequirement.PREFERRED,
            ),
            exclude_credentials=exclude_creds,
        )
        session["webauthn_registration_challenge"] = _b64url_encode(options.challenge)
        import json as _json
        return jsonify({"ok": True, "options": _json.loads(options_to_json(options))})

    @app.route("/api/auth/passkey/register/finish", methods=["POST"])
    @login_required
    def passkey_register_finish():
        if not _HAS_WEBAUTHN:
            return jsonify({"ok": False, "error": "WebAuthn backend not installed"}), 501
        payload = request.get_json(silent=True) or {}
        challenge = session.get("webauthn_registration_challenge")
        if not challenge:
            return jsonify({"ok": False, "error": "Missing registration challenge"}), 400
        try:
            verification = verify_registration_response(
                credential=payload,
                expected_challenge=_b64url_decode(challenge),
                expected_rp_id=WEB_UI_RP_ID,
                expected_origin=WEB_UI_ORIGIN,
            )
            creds = _load_webauthn_credentials()
            creds.append({
                "credential_id": _b64url_encode(verification.credential_id),
                "public_key": _b64url_encode(verification.credential_public_key),
                "sign_count": verification.sign_count,
                "transports": payload.get("response", {}).get("transports", []),
            })
            _save_webauthn_credentials(creds)
            session.pop("webauthn_registration_challenge", None)
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 400

    @app.route("/api/auth/passkey/login/begin", methods=["POST"])
    def passkey_login_begin():
        if not _HAS_WEBAUTHN:
            return jsonify({"ok": False, "error": "WebAuthn backend not installed"}), 501
        payload = request.get_json(silent=True) or {}
        username = payload.get("username", WEB_UI_USERNAME)
        if username != WEB_UI_USERNAME:
            return jsonify({"ok": False, "error": "Invalid credentials"}), 401
        creds = _load_webauthn_credentials()
        if not creds:
            return jsonify({"ok": False, "error": "Passkey not configured"}), 400
        allow_creds = [PublicKeyCredentialDescriptor(id=_b64url_decode(c["credential_id"])) for c in creds]
        options = generate_authentication_options(
            rp_id=WEB_UI_RP_ID,
            allow_credentials=allow_creds,
            user_verification=UserVerificationRequirement.PREFERRED,
        )
        session["webauthn_auth_challenge"] = _b64url_encode(options.challenge)
        import json as _json
        return jsonify({"ok": True, "options": _json.loads(options_to_json(options))})

    @app.route("/api/auth/passkey/login/finish", methods=["POST"])
    def passkey_login_finish():
        if not _HAS_WEBAUTHN:
            return jsonify({"ok": False, "error": "WebAuthn backend not installed"}), 501
        payload = request.get_json(silent=True) or {}
        challenge = session.get("webauthn_auth_challenge")
        if not challenge:
            return jsonify({"ok": False, "error": "Missing authentication challenge"}), 400
        creds = _load_webauthn_credentials()
        cred_id = payload.get("id")
        match = next((c for c in creds if c["credential_id"] == cred_id), None)
        if not match:
            return jsonify({"ok": False, "error": "Invalid credentials"}), 401
        try:
            verification = verify_authentication_response(
                credential=payload,
                expected_challenge=_b64url_decode(challenge),
                expected_rp_id=WEB_UI_RP_ID,
                expected_origin=WEB_UI_ORIGIN,
                credential_public_key=_b64url_decode(match["public_key"]),
                credential_current_sign_count=int(match.get("sign_count", 0)),
            )
            match["sign_count"] = verification.new_sign_count
            _save_webauthn_credentials(creds)
            session.pop("webauthn_auth_challenge", None)
            session["logged_in"] = True
            session.permanent = True
            return jsonify({"ok": True, "redirect": url_for("index")})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 401

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

    _version_cache: dict = {"ts": 0, "latest": None}

    @app.route("/api/version")
    @login_required
    def api_version():
        import urllib.request, urllib.error, json as _json
        try:
            from version import __version__ as _app_ver, GITHUB_REPO as _repo
        except ImportError:
            _app_ver, _repo = "unknown", "dzaczek/Meshtastic-AI-Bridge"

        now = time.time()
        latest = _version_cache.get("latest")
        if not latest or now - _version_cache["ts"] > 3600:
            try:
                url = f"https://api.github.com/repos/{_repo}/releases/latest"
                req = urllib.request.Request(url, headers={"User-Agent": "MeshtasticAIBridge"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    gh = _json.loads(resp.read().decode())
                latest = gh.get("tag_name", "").lstrip("v")
                _version_cache["latest"] = latest
                _version_cache["ts"] = now
            except Exception:
                latest = _version_cache.get("latest")  # keep stale if error

        return jsonify({
            "running":   _app_ver,
            "latest":    latest,
            "repo":      _repo,
            "up_to_date": (latest == _app_ver) if latest else None,
        })

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
        try:
            from version import __version__ as _av
            st["app_version"] = _av
        except ImportError:
            pass
        elapsed = int(time.time() - st.pop("uptime_start"))
        h, r = divmod(elapsed, 3600)
        m, s = divmod(r, 60)
        st["uptime_s"]   = elapsed
        st["uptime_str"] = f"{h:02d}:{m:02d}:{s:02d}"
        st["bot_name"]   = _bot_name

        # Inject total tokens from db instead of static _status tracking
        if _HAS_NODE_DB:
            try:
                db_stats = _node_db.get_token_stats()
                # Using month stats as a proxy for total, or just query total
                if 'total' in db_stats:
                    st['ai_tokens_in'] = db_stats['total']['tokens_in']
                    st['ai_tokens_out'] = db_stats['total']['tokens_out']
            except Exception:
                pass

        # Real link health: check last received packet time
        if _meshtastic_handler:
            last_rx = _meshtastic_handler.last_rx_time
            if last_rx:
                ago = int(time.time() - last_rx)
                st["last_rx_ago_s"] = ago
                st["last_rx_str"]   = _fmt_age(ago)
                # If state-machine says connected but radio is silent > 3 min → warn
                if st.get("connected") and ago > 180:
                    st["link_stale"] = True
                    st["connected"]  = False   # correct the displayed status
            else:
                st["last_rx_ago_s"] = None
                st["last_rx_str"]   = "no data"

            # Firmware version
            try:
                my_num = _meshtastic_handler.node_id
                nodes  = getattr(_meshtastic_handler.interface, 'nodes', None) or {}
                for nd in nodes.values():
                    if nd.get('num') == my_num:
                        meta = nd.get('metadata', {}) or {}
                        fw   = (meta.get('firmwareVersion')
                                or meta.get('firmware_version')
                                or getattr(_meshtastic_handler.interface, 'metadata', {})
                                   .get('firmwareVersion', ''))
                        if fw:
                            st['firmware_version'] = fw
                        break
            except Exception:
                pass
            # Expose radio preset from device so UI can show it
            try:
                node = _meshtastic_handler.interface.getNode('^local')
                lc   = getattr(node, 'localConfig', None)
                if lc and hasattr(lc, 'lora'):
                    PRESETS = {0:'LONG_FAST',1:'LONG_SLOW',2:'VERY_LONG_SLOW',
                               3:'MEDIUM_SLOW',4:'MEDIUM_FAST',5:'SHORT_SLOW',
                               6:'SHORT_FAST',7:'LONG_MODERATE',8:'SHORT_TURBO'}
                    REGIONS = {0:'UNSET',1:'US',2:'EU_433',3:'EU_868',4:'CN',
                               5:'JP',6:'ANZ',7:'KR',8:'TW',9:'RU',10:'IN'}
                    preset_id = int(lc.lora.modem_preset)
                    region_id = int(lc.lora.region)
                    st["radio_preset"] = PRESETS.get(preset_id, str(preset_id))
                    st["radio_region"] = REGIONS.get(region_id, str(region_id))
                    st["radio_hops"]   = int(lc.lora.hop_limit)
            except Exception:
                pass

        return jsonify(st)

    @app.route("/api/send", methods=["POST"])
    @login_required
    def api_send():
        data        = request.get_json(silent=True) or {}
        text        = (data.get("text") or "").strip()
        channel     = int(data.get("channel", 0))
        destination = (data.get("destination") or "").strip()   # hex node id for DM
        if not text:
            return jsonify({"ok": False, "error": "Empty message"}), 400
        if not _send_callback:
            return jsonify({"ok": False, "error": "Send callback not configured"}), 503
        try:
            ok, reason = _send_callback(text, channel, destination or None)
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        if ok:
            sender = get_bot_name()
            is_dm  = bool(destination)
            web_id = add_message(text, sender, channel, "tx",
                                 sender_id=_status.get("node_id", ""),
                                 destination_id=destination,
                                 ack="pending")
            if is_dm and _meshtastic_handler:
                # DM: wait for radio ACK packet
                pkt_id = _meshtastic_handler._last_tx_packet_id
                if pkt_id:
                    _pending_acks[int(pkt_id)] = web_id
            else:
                # Channel broadcast: no radio ACK expected, mark sent immediately
                update_message_ack(web_id, "ok")
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


    @app.route("/api/analytics/node/<node_id>")
    @login_required
    def api_analytics_node(node_id):
        if not _HAS_NODE_DB:
            return jsonify({"error": "node_db not available"}), 503

        if "hours" in request.args:
            hours = float(request.args.get("hours"))
        else:
            hours = float(request.args.get("days", 7)) * 24.0

        hide_broadcast = request.args.get("hide_broadcast", "0") == "1"
        stats = _node_db.get_per_node_analytics(node_id, hours=hours, hide_broadcast=hide_broadcast)

        iface = getattr(_meshtastic_handler, "interface", None)
        for key in ("top_receivers", "top_receivers_text"):
            for r in stats.get(key, []):
                r["name"] = _node_name(r["id"], iface)
        for key in ("top_senders", "top_senders_text"):
            for s in stats.get(key, []):
                s["name"] = _node_name(s["id"], iface)

        return jsonify(stats)

    @app.route("/api/analytics/packets")
    @login_required
    def api_analytics_packets():
        if not _HAS_NODE_DB:
            return jsonify({"error": "node_db not available"}), 503

        if "hours" in request.args:
            hours = float(request.args.get("hours"))
        else:
            hours = float(request.args.get("days", 7)) * 24.0

        portnum_filter = request.args.get("portnum") or None
        hide_broadcast = request.args.get("hide_broadcast", "0") == "1"

        stats = _node_db.get_packet_analytics(hours=hours, portnum_filter=portnum_filter, hide_broadcast=hide_broadcast)

        iface = getattr(_meshtastic_handler, "interface", None)
        if "top_senders" in stats:
            for s in stats["top_senders"]:
                s["name"] = _node_name(s["id"], iface)
        for link_key in ("top_links", "top_links_text", "encrypted_links"):
            for l in stats.get(link_key, []):
                l["from_name"] = _node_name(l["from"], iface)
                l["to_name"]   = _node_name(l["to"],   iface)
        for s in stats.get("encrypted_senders", []):
            s["name"] = _node_name(s["id"], iface)

        return jsonify(stats)

    @app.route("/api/clear_error", methods=["POST"])
    @login_required
    def api_clear_error():
        with _lock:
            _status["last_error"] = None
        return jsonify({"ok": True})

    @app.route("/api/ai/enabled")
    @login_required
    def api_ai_enabled():
        return jsonify({"enabled": _status.get("ai_enabled", True)})

    @app.route("/api/ai/toggle", methods=["POST"])
    @login_required
    def api_ai_toggle():
        with _lock:
            current = _status.get("ai_enabled", True)
            _status["ai_enabled"] = not current
        _save_ui_settings()
        return jsonify({"enabled": _status["ai_enabled"]})

    @app.route("/api/bot/private_replies")
    @login_required
    def api_bot_private_replies_get():
        return jsonify({"private": _status.get("bot_private_replies", False)})

    @app.route("/api/bot/private_replies/toggle", methods=["POST"])
    @login_required
    def api_bot_private_replies_toggle():
        with _lock:
            current = _status.get("bot_private_replies", False)
            _status["bot_private_replies"] = not current
        _save_ui_settings()
        return jsonify({"private": _status["bot_private_replies"]})

    @app.route("/api/sys_packets_to_chat")
    @login_required
    def api_sys_packets_to_chat_get():
        return jsonify({"enabled": _status.get("sys_packets_to_chat", False)})

    @app.route("/api/sys_packets_to_chat/toggle", methods=["POST"])
    @login_required
    def api_sys_packets_to_chat_toggle():
        with _lock:
            current = _status.get("sys_packets_to_chat", False)
            _status["sys_packets_to_chat"] = not current
        _save_ui_settings()
        return jsonify({"enabled": _status["sys_packets_to_chat"]})

    @app.route("/api/ai/token_stats")
    @login_required
    def api_ai_token_stats():
        if not _HAS_NODE_DB:
            return jsonify({"total": {"tokens_in": 0, "tokens_out": 0}, "month": {"tokens_in": 0, "tokens_out": 0}, "daily": [], "top_users": []})
        try:
            return jsonify(_node_db.get_token_stats())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/ai/token_categories")
    @login_required
    def api_ai_token_categories():
        if not _HAS_NODE_DB:
            return jsonify([])
        try:
            days = int(request.args.get("days", 30))
            return jsonify(_node_db.get_token_by_category(days))
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ------------------------------------------------------------------
    # Dashboard layout persistence
    # ------------------------------------------------------------------

    @app.route("/api/layout/<layout_id>")
    @login_required
    def api_layout_get(layout_id):
        try:
            if os.path.exists(_LAYOUTS_PATH):
                with open(_LAYOUTS_PATH) as f:
                    layouts = json.load(f)
                return jsonify({"layout": layouts.get(layout_id, [])})
        except Exception:
            pass
        return jsonify({"layout": []})

    @app.route("/api/layout/<layout_id>", methods=["POST"])
    @login_required
    def api_layout_save(layout_id):
        data = request.get_json(silent=True) or {}
        layout = data.get("layout", [])
        try:
            layouts = {}
            if os.path.exists(_LAYOUTS_PATH):
                with open(_LAYOUTS_PATH) as f:
                    layouts = json.load(f)
            layouts[layout_id] = layout
            os.makedirs(os.path.dirname(_LAYOUTS_PATH), exist_ok=True)
            with open(_LAYOUTS_PATH, "w") as f:
                json.dump(layouts, f)
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

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

    @app.route("/api/node/<node_id>/traces")
    @login_required
    def api_node_traces(node_id):
        if not _HAS_NODE_DB:
            return jsonify({"traces": []})
        limit = min(int(request.args.get("limit", 50)), 200)
        return jsonify({"traces": _node_db.get_traceroutes(node_id, limit=limit)})

    # Cache for liamcottle.net node list (~5MB, refreshed every 10 min)
    _netinfo_cache: dict = {"ts": 0, "by_hex": {}, "by_int": {}}
    _netinfo_lock = threading.Lock()

    @app.route("/api/node/<node_id>/netinfo")
    @login_required
    def api_node_netinfo(node_id):
        """Fetch node data from meshtastic.liamcottle.net (public MQTT aggregator)."""
        import urllib.request, urllib.error, json as _json
        node_hex = node_id.lstrip("!").lower()
        try:
            node_int = int(node_hex, 16)
        except ValueError:
            return jsonify({"ok": False, "error": "Invalid node id"}), 400

        SOURCE_URL = "https://meshtastic.liamcottle.net/api/v1/nodes"
        CACHE_TTL  = 600  # 10 minutes

        now = time.time()
        with _netinfo_lock:
            cache_age = now - _netinfo_cache["ts"]
            need_refresh = cache_age > CACHE_TTL

        if need_refresh:
            try:
                req = urllib.request.Request(
                    SOURCE_URL,
                    headers={"User-Agent": "MeshtasticAIBridge/1.0",
                             "Accept": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    raw = _json.loads(resp.read().decode("utf-8", errors="replace"))
                nodes_list = raw.get("nodes", raw) if isinstance(raw, dict) else raw
                by_hex = {}
                by_int = {}
                by_neighbour = {}   # node_int_str -> [{"reporter_hex","reporter_name","snr","ts"}]
                for n in nodes_list:
                    if not isinstance(n, dict):
                        continue
                    h = str(n.get("node_id_hex", "") or "").lower().lstrip("!")
                    if h:
                        by_hex[h] = n
                    nid = str(n.get("node_id", "") or "")
                    if nid:
                        by_int[nid] = n
                    # Index neighbours this node has heard via radio
                    nbs = n.get("neighbours") or []
                    if not isinstance(nbs, list):
                        continue
                    for nb in nbs:
                        if not isinstance(nb, dict):
                            continue
                        nb_id = str(nb.get("node_id", "") or "")
                        if not nb_id:
                            continue
                        by_neighbour.setdefault(nb_id, []).append({
                            "reporter_hex":  h,
                            "reporter_name": n.get("long_name") or n.get("short_name") or h,
                            "snr":           nb.get("snr"),
                            "ts":            n.get("neighbours_updated_at"),
                        })
                with _netinfo_lock:
                    _netinfo_cache["by_hex"] = by_hex
                    _netinfo_cache["by_int"] = by_int
                    _netinfo_cache["by_neighbour"] = by_neighbour
                    _netinfo_cache["ts"] = time.time()
                    cache_age = 0
            except Exception as e:
                return jsonify({"ok": False, "error": f"Fetch failed: {str(e)[:200]}",
                                "source": SOURCE_URL}), 502

        with _netinfo_lock:
            by_hex      = _netinfo_cache.get("by_hex", {})
            by_int      = _netinfo_cache.get("by_int", {})
            by_nb       = _netinfo_cache.get("by_neighbour", {})
            total_cached = len(by_hex)
            node_data   = by_hex.get(node_hex) or by_int.get(str(node_int))
            reporters   = by_nb.get(str(node_int), [])

        if not node_data:
            return jsonify({
                "ok": False,
                "error": f"Node !{node_hex} not in public database ({total_cached} nodes). "
                         f"No MQTT-connected node reports it directly.",
                "source": SOURCE_URL,
                "cache_age_s": int(cache_age),
                "reporters": reporters[:20],   # nodes that heard this node
                "reporters_count": len(reporters),
            })

        # Save snapshot to node_db (telemetry, position, full JSON blob)
        if _HAS_NODE_DB:
            try:
                _node_db.add_net_snapshot(node_hex, node_data, source="liamcottle")
            except Exception:
                pass

        return jsonify({
            "ok": True,
            "node_id": node_hex,
            "source": SOURCE_URL,
            "cache_age_s": int(cache_age),
            "data": node_data,
        })

    @app.route("/api/node/<node_id>/net_history")
    @login_required
    def api_node_net_history(node_id):
        if not _HAS_NODE_DB:
            return jsonify({"snapshots": []})
        limit = min(int(request.args.get("limit", 100)), 500)
        snaps = _node_db.get_net_snapshots(node_id, limit=limit)
        return jsonify({"snapshots": snaps})

    # ------------------------------------------------------------------
    # Device configuration
    # ------------------------------------------------------------------

    @app.route("/api/config")
    @login_required
    def api_config():
        if not _meshtastic_handler:
            return jsonify({"_error": "Not connected"}), 503
        cfg = _meshtastic_handler.get_device_config()
        # Annotate each channel with its computed hash (for PSK debugging)
        try:
            node = _meshtastic_handler.interface.getNode('^local')
            if hasattr(node, 'get_channels_with_hash'):
                hash_map = {c['index']: c['hash'] for c in node.get_channels_with_hash()}
                for ch in cfg.get('channels', []):
                    ch['_hash'] = hash_map.get(ch.get('index'), None)
        except Exception:
            pass
        return jsonify(cfg)

    @app.route("/api/traceroutes")
    @login_required
    def api_traceroutes():
        since = float(request.args.get("since", 0))
        with _lock:
            rows = [t for t in _traceroutes if t["ts"] > since]
        return jsonify({"traceroutes": rows, "ts": time.time()})

    @app.route("/api/traceroute/<dest_id>", methods=["POST"])
    @login_required
    def api_send_traceroute(dest_id):
        if not _meshtastic_handler:
            return jsonify({"ok": False, "error": "Not connected"}), 503
        hops = int(request.args.get("hops", 7))
        ok, msg = _meshtastic_handler.send_traceroute(dest_id, hop_limit=hops)
        return jsonify({"ok": ok, "message": msg, "sent_at": time.time()})

    @app.route("/api/config/fixed_position", methods=["GET"])
    @login_required
    def api_get_fixed_position():
        """Return what the device is currently broadcasting as its position."""
        if not _meshtastic_handler:
            return jsonify({"ok": False, "error": "Not connected"}), 503
        pos = _meshtastic_handler.get_own_position()
        if not pos:
            return jsonify({"ok": False, "error": "Position unavailable"})
        return jsonify({"ok": True, "position": pos})

    @app.route("/api/config/fixed_position", methods=["POST"])
    @login_required
    def api_set_fixed_position():
        if not _meshtastic_handler:
            return jsonify({"ok": False, "error": "Not connected"}), 503
        data = request.get_json(silent=True) or {}
        try:
            lat = float(data["lat"])
            lon = float(data["lon"])
            alt = int(data.get("alt", 0))
        except (KeyError, ValueError) as e:
            return jsonify({"ok": False, "error": f"Bad parameters: {e}"}), 400
        reboot = bool(data.get("reboot", False))
        ok, msg = _meshtastic_handler.set_fixed_position(lat, lon, alt, reboot=reboot)
        # Immediately update position_history in DB so map/cache reflects new position
        if ok and _HAS_NODE_DB and _meshtastic_handler.node_id:
            try:
                _node_db.add_position(
                    f"{_meshtastic_handler.node_id:x}", lat, lon, alt
                )
            except Exception:
                pass
        return jsonify({"ok": ok, "message": msg, "rebooting": reboot and ok})

    @app.route("/api/config/fixed_position", methods=["DELETE"])
    @login_required
    def api_remove_fixed_position():
        if not _meshtastic_handler:
            return jsonify({"ok": False, "error": "Not connected"}), 503
        ok, msg = _meshtastic_handler.remove_fixed_position()
        return jsonify({"ok": ok, "message": msg})

    @app.route("/api/device/reboot", methods=["POST"])
    @login_required
    def api_device_reboot():
        if not _meshtastic_handler:
            return jsonify({"ok": False, "error": "Not connected"}), 503
        try:
            node = _meshtastic_handler.interface.getNode('^local')
            node.reboot()
            return jsonify({"ok": True, "message": "Reboot command sent to device"})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/device/reconnect", methods=["POST"])
    @login_required
    def api_device_reconnect():
        if not _meshtastic_handler:
            return jsonify({"ok": False, "error": "No handler"}), 503
        threading.Thread(target=_meshtastic_handler._do_reconnect, daemon=True).start()
        return jsonify({"ok": True, "message": "Reconnect triggered"})

    @app.route("/api/device/disconnect", methods=["POST"])
    @login_required
    def api_device_disconnect():
        if not _meshtastic_handler or not _meshtastic_handler.interface:
            return jsonify({"ok": False, "error": "Not connected"}), 503
        try:
            _meshtastic_handler.interface.close()
            return jsonify({"ok": True, "message": "Disconnected"})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/device/info")
    @login_required
    def api_device_info():
        if not _meshtastic_handler or not _meshtastic_handler.interface:
            return jsonify({"error": "Not connected"}), 503
        my_num = _meshtastic_handler.node_id
        nodes = getattr(_meshtastic_handler.interface, 'nodes', None) or {}
        own = None
        for nd in nodes.values():
            if nd.get('num') == my_num:
                own = nd
                break
        base = {"id": f"{my_num:x}" if my_num else ""}
        if not own:
            base["error"] = "node_not_in_cache"
            return jsonify(base)
        user    = own.get('user', {})
        metrics = own.get('deviceMetrics') or {}
        pos     = own.get('position') or {}
        lat     = pos.get('latitude')
        lon     = pos.get('longitude')
        voltage = metrics.get('voltage')
        base.update({
            "long_name":   user.get('longName', ''),
            "short_name":  user.get('shortName', ''),
            "hw_model":    user.get('hwModel', ''),
            "battery":     metrics.get('batteryLevel') or own.get('batteryLevel'),
            "voltage":     round(float(voltage), 2) if voltage else None,
            "uptime_s":    metrics.get('uptimeSeconds') or own.get('uptimeSeconds'),
            "channel_util": metrics.get('channelUtilization'),
            "air_util_tx": metrics.get('airUtilTx'),
            "lat":         float(lat) if lat else None,
            "lon":         float(lon) if lon else None,
            "altitude":    pos.get('altitude'),
            "last_heard":  own.get('lastHeard'),
            "is_licensed": bool(user.get('isLicensed', False)),
        })
        return jsonify(base)

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

    @app.route("/api/config/export_url")
    @login_required
    def api_config_export_url():
        if not _meshtastic_handler:
            return jsonify({"ok": False, "error": "Not connected"}), 503
        url = _meshtastic_handler.get_channels_url()
        return jsonify({"ok": True, "url": url})

    @app.route("/api/config/import_url", methods=["POST"])
    @login_required
    def api_config_import_url():
        if not _meshtastic_handler:
            return jsonify({"ok": False, "error": "Not connected"}), 503
        data = request.get_json(silent=True) or {}
        url = data.get("url", "")
        if not url:
            return jsonify({"ok": False, "error": "No URL provided"}), 400
        ok, msg = _meshtastic_handler.set_channels_url(url)
        return jsonify({"ok": ok, "message": msg})

    @app.route("/api/config/import_channels", methods=["POST"])
    @login_required
    def api_config_import_channels():
        if not _meshtastic_handler:
            return jsonify({"ok": False, "error": "Not connected"}), 503
        data = request.get_json(silent=True) or {}
        channels = data.get("channels", [])
        if not channels:
            return jsonify({"ok": False, "error": "No channels provided"}), 400

        success_count = 0
        errors = []
        for ch in channels:
            ok, msg = _meshtastic_handler.set_device_config("channel", ch)
            if ok:
                success_count += 1
            else:
                errors.append(f"Ch {ch.get('index', '?')}: {msg}")

        if errors:
            return jsonify({"ok": False, "message": f"Imported {success_count} channels. Errors: " + ", ".join(errors)})
        return jsonify({"ok": True, "message": f"Imported {success_count} channels successfully"})

    @app.route("/api/qrcode")
    @login_required
    def api_qrcode():
        data = request.args.get("data", "")
        if not data:
            return jsonify({"error": "No data provided"}), 400
        try:
            import qrcode
            import io
            from flask import send_file
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=5,
                border=4,
            )
            qr.add_data(data)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            img_io = io.BytesIO()
            img.save(img_io, 'PNG')
            img_io.seek(0)
            return send_file(img_io, mimetype='image/png')
        except ImportError:
            return jsonify({"error": "qrcode library not installed"}), 500
        except Exception as e:
            return jsonify({"error": str(e)}), 500


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

    def _periodic_save():
        """Save chat history every 5 minutes regardless of activity."""
        while True:
            time.sleep(300)
            _save_chat_history()

    def _run():
        logger.info(f"web_ui: listening on http://{host}:{port}")
        add_message(f"Web UI available on port {port}", "system", -1, "system")
        try:
            from werkzeug.serving import run_simple
            run_simple(host, port, app, threaded=True, use_reloader=False)
        except Exception:
            app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)

    threading.Thread(target=_periodic_save, daemon=True, name="ChatHistorySave").start()
    _server_thread = threading.Thread(target=_run, daemon=True, name="WebUI")
    _server_thread.start()
    return _server_thread
