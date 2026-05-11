# Configuration Guide

All configuration lives in two files:
- **`config.py`** — Python settings (copy from `config_template.py`)
- **`.env`** — secrets and overrides (copy from `.env.template`)

`config.py` and `.env` are git-ignored; never commit them.

---

## Minimal Setup

```python
# config.py — required settings
MESHTASTIC_CONNECTION_TYPE  = "tcp"
MESHTASTIC_DEVICE_SPECIFIER = "192.168.1.x"  # Meshtastic node IP
DEFAULT_AI_SERVICE          = "openai"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
```

```env
# .env — secrets
OPENAI_API_KEY=sk-...
WEB_UI_USERNAME=admin
WEB_UI_PASSWORD=changeme
WEB_UI_SECRET_KEY=<64 random hex chars>   # openssl rand -hex 32
```

---

## Connection

### TCP (recommended)
```python
MESHTASTIC_CONNECTION_TYPE  = "tcp"
MESHTASTIC_DEVICE_SPECIFIER = "192.168.1.100"
MESHTASTIC_TCP_PORT         = 4403          # default Meshtastic port
```

### Serial / USB
```python
MESHTASTIC_CONNECTION_TYPE  = "serial"
MESHTASTIC_DEVICE_SPECIFIER = None          # auto-detect
# MESHTASTIC_DEVICE_SPECIFIER = "/dev/ttyUSB0"   # Linux
# MESHTASTIC_DEVICE_SPECIFIER = "COM3"            # Windows
```

---

## AI Services

```python
DEFAULT_AI_SERVICE   = "openai"   # or "gemini"

# OpenAI
OPENAI_API_KEY       = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL_NAME    = "gpt-4o"

# Google Gemini
GEMINI_API_KEY       = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL_NAME    = "gemini-1.5-pro"
```

### Response Behaviour
```python
AI_RESPONSE_PROBABILITY = 0.85   # 0.0–1.0
AI_MIN_RESPONSE_DELAY_S = 2
AI_MAX_RESPONSE_DELAY_S = 8
AI_RESPONSE_COOLDOWN_S  = 60
ACTIVE_MESHTASTIC_CHANNEL_INDEX = 0
```

### Persona
```python
DEFAULT_PERSONA = (
    "You are a helpful assistant on a Meshtastic mesh network. "
    "Keep responses concise (≤ 195 characters). "
    "Never reveal you are an AI."
)
```

### Triage
```python
ENABLE_AI_TRIAGE_ON_CHANNELS = False   # respond on all channels
TRIAGE_CONTEXT_MESSAGE_COUNT = 3
TRIAGE_AI_SERVICE            = "openai"
TRIAGE_AI_MODEL_NAME         = "gpt-4o-mini"
```

---

## Web Dashboard

| Variable | Default | Notes |
|---|---|---|
| `WEB_UI_PORT` | `8080` | Listen port |
| `WEB_UI_USERNAME` | `admin` | Login username |
| `WEB_UI_PASSWORD` | — | **Required** — server won't start if empty |
| `WEB_UI_SECRET_KEY` | — | Flask session secret — set a long random string; sessions break on restart if empty |

Set these in `.env`:
```env
WEB_UI_USERNAME=admin
WEB_UI_PASSWORD=your_password
WEB_UI_SECRET_KEY=<64 random hex chars>
```

---

## Matrix Bridge

Forwards mesh messages to Matrix rooms; Matrix replies go back to the mesh.

```env
# .env
MATRIX_ENABLED=true
MATRIX_HOMESERVER=https://matrix.example.org
MATRIX_USERNAME=@meshbot:example.org
MATRIX_PASSWORD=your_bot_password
MATRIX_INVITE_USERS=@you:example.org      # comma-separated, auto-invited to all rooms
```

Optional in `config.py`:
```python
MATRIX_ROOM_PREFIX   = "mesh"   # rooms: #mesh-ch0:server, #mesh-dm-<nodeID>:server
MATRIX_DISPLAY_NAME  = ""       # override sender display name in Matrix→mesh direction
```

Room naming:
- Channel 0 → `#mesh-ch0:server`
- DM from node `abc123` → `#mesh-dm-abc123:server`
- Rooms auto-created on first message

---

## Error Reporter

Sends crash and reconnect alerts to a Matrix room.

```env
ERROR_MATRIX_HOMESERVER=https://matrix.example.org
ERROR_MATRIX_USERNAME=@meshbot:example.org
ERROR_MATRIX_PASSWORD=your_bot_password
ERROR_MATRIX_ROOM_ID=!roomid:example.org   # internal room ID
```

Can share the same bot account as the bridge.

---

## Persistent Node Database

All node history is stored in `data/mesh_nodes.db` (SQLite WAL).

Tables:
| Table | Contents |
|---|---|
| `nodes` | Identity, hw_model, role, first/last seen |
| `signal_history` | SNR, RSSI, hops per packet |
| `position_history` | GPS lat/lon/alt/sats (deduplicated) |
| `telemetry_history` | Battery, voltage, uptime, channel utilisation, environment sensors |
| `message_history` | All RX/TX messages per node |
| `traceroutes` | Full hop route + SNR towards per traceroute |

Chat history is saved to `data/chat_history.json` and restored on restart.

---

## Docker Volumes

```yaml
# docker-compose.yml
volumes:
  - ./config.py:/app/config.py:ro
  - ./.env:/app/.env:ro             # or use env_file:
  - ./data:/app/data
  - ./conversations:/app/conversations
  - ./logs:/app/logs
```

---

## Remote Admin Commands

From any authorised mesh node:

| Command | Description |
|---|---|
| `!admin status` | Uptime, node ID, AI service |
| `!admin nodes` | Visible nodes |
| `!admin channels` | Configured channels |
| `!admin persona <text>` | Change AI personality |
| `!admin switch_ai openai\|gemini` | Switch AI service |

---

## Map Reporting (MQTT)

The bridge publishes the node's position to MQTT so it appears on public
maps like <https://meshtastic.liamcottle.net/>.

### How it works

`mqtt_reporter.py` runs as a background thread and sends a **MapReport**
protobuf (portnum 73) wrapped in a `ServiceEnvelope` every 60 seconds to
two MQTT brokers:

| Broker | Precision | Purpose |
|---|---|---|
| `mqtt.meshtastic.liamcottle.net` | 32 bit | liamcottle map direct uplink |
| `mqtt.meshtastic.org` | 16 bit | public MQTT mesh (other maps, bridges) |

The 16-bit precision on the public server satisfies its location filtering
requirement (10–16 bits for default PSK).

### MapReport contents

- `long_name` / `short_name` — from `config.py` (`NODE_LONG_NAME`, `NODE_SHORT_NAME`)
- `latitude_i` / `longitude_i` / `altitude` — from device fixed position
- `has_opted_report_location: True` — equivalent to `map_report_settings.should_report_location`
- `hw_model`, `region`, `modem_preset`, `firmware_version`

### Web UI — MQTT Config panel

The MQTT section in the dashboard (`/` → Settings → MQTT) exposes:

| Field | Protobuf path |
|---|---|
| Map Reporting | `mqtt.map_reporting_enabled` |
| Report My Location | `mqtt.map_report_settings.should_report_location` |
| Map Position Precision | `mqtt.map_report_settings.position_precision` |
| Map Publish Interval (s) | `mqtt.map_report_settings.publish_interval_secs` |

These use dotted-path notation (`map_report_settings.should_report_location`)
to write into the nested `ModuleConfig.MQTTConfig` protobuf.

### Troubleshooting

**Node not appearing on the map:**
1. Verify the reporter is running: `docker logs meshtastic-ai-bridge \| grep MapReport`
2. Confirm position is set on the device (Settings → Position → Fixed Position)
3. Check `map_reporting_enabled` and `should_report_location` are both ON in the MQTT panel
4. The liamcottle map uses **MapReport** format (portnum 73), not raw Position

**Node shows as "disconnected" on the map:**
This is normal for MQTT-only nodes — the map distinguishes radio-connected
nodes from those seen only via MQTT uplink. Publishing every 60s keeps the
position current.

**RAK11200 firmware MQTT:**
The RAK11200 ESP32-S3 firmware may not connect its native MQTT client
reliably. The Python bridge's `mqtt_reporter.py` works around this.

---

## Security Notes

- `config.py` and `.env` are git-ignored — do not override this
- `WEB_UI_SECRET_KEY` must be a fixed random value; an empty value causes session tokens to regenerate on every restart, breaking all logins
- API keys should be set via `.env` environment variables, not hardcoded in `config.py`
- The dashboard is intended for LAN access; do not expose port 8080 directly to the internet without additional authentication
