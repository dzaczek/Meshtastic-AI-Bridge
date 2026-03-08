# --- config_template.py ---
# Copy this to config.py and fill in your values.
# API keys should go in .env file (see .env.template).
import os
from dotenv import load_dotenv

load_dotenv()

# --- API Keys (from .env) ---
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# --- Meshtastic Connection Settings ---
MESHTASTIC_CONNECTION_TYPE = os.environ.get("MESHTASTIC_CONNECTION_TYPE", "serial")
MESHTASTIC_DEVICE_SPECIFIER = os.environ.get("MESHTASTIC_DEVICE_SPECIFIER", "") or None

ACTIVE_MESHTASTIC_CHANNEL_INDEX = 0

# --- Feature Switches ---
# Set to False to disable AI responses entirely (bridge/TUI still work)
AI_ENABLED = os.environ.get("AI_ENABLED", "true").lower() in ("true", "1", "yes")
# Set to False to disable bot commands (ping, info, traceroute, !admin)
BOT_COMMANDS_ENABLED = os.environ.get("BOT_COMMANDS_ENABLED", "true").lower() in ("true", "1", "yes")

# --- AI Settings ---
DEFAULT_AI_SERVICE = os.environ.get("DEFAULT_AI_SERVICE", "openai")

# AI Response Settings
AI_RESPONSE_PROBABILITY = 0.85
AI_MIN_RESPONSE_DELAY_S = 2
AI_MAX_RESPONSE_DELAY_S = 8
AI_RESPONSE_COOLDOWN_S = 60

# AI Triage Settings
ENABLE_AI_TRIAGE_ON_CHANNELS = False
TRIAGE_CONTEXT_MESSAGE_COUNT = 3
TRIAGE_AI_SERVICE = "openai"
TRIAGE_AI_MODEL_NAME = "gpt-3.5-turbo"

# Conversation History Settings
MAX_HISTORY_MESSAGES_FOR_CONTEXT = 10
SUMMARIZE_THRESHOLD_TOKENS = 1000

# --- Model Settings ---
OPENAI_MODEL_NAME = "gpt-4o"
OPENAI_VISION_MODEL_NAME = "gpt-4-vision-preview"

GEMINI_MODEL_NAME = "gemini-1.5-pro"
GEMINI_VISION_MODEL_NAME = "gemini-pro-vision"
GEMINI_TEXT_MODEL_NAME = "gemini-1.5-flash-latest"

# --- Connection Settings ---
INITIAL_CONNECTION_MAX_RETRIES = 10
INITIAL_CONNECTION_RETRY_DELAY = 5
MONITOR_CONNECTION_INTERVAL = 30
RECONNECTION_MAX_RETRIES = 3
RECONNECTION_RETRY_DELAY = 15

# --- Web Settings ---
MAX_WEB_SUMMARY_LENGTH = 1800
WEB_UTILS_TIMEOUT = 20

# --- Admin node IDs (hex, lowercase, no '!' prefix) ---
ADMIN_NODE_IDS = []

# --- Matrix Bridge Settings ---
MATRIX_ENABLED = os.environ.get("MATRIX_ENABLED", "false").lower() in ("true", "1", "yes")
MATRIX_HOMESERVER = os.environ.get("MATRIX_HOMESERVER", "https://matrix.org")
MATRIX_USERNAME = os.environ.get("MATRIX_USERNAME", "")
MATRIX_PASSWORD = os.environ.get("MATRIX_PASSWORD", "")
MATRIX_ROOM_PREFIX = "mesh"  # rooms will be #mesh-ch0, #mesh-ch1, #mesh-dm
MATRIX_INVITE_USERS = [u.strip() for u in os.environ.get("MATRIX_INVITE_USERS", "").split(",") if u.strip()]
# Override display name for Matrix->Mesh messages (empty = use Matrix profile name)
MATRIX_DISPLAY_NAME = os.environ.get("MATRIX_DISPLAY_NAME", "")

# --- Bot Identity ---
BOT_NAME = "Eva"

# --- Default AI Persona ---
DEFAULT_PERSONA = (
    "You are Eva -- a real person hanging out on a Meshtastic LoRa mesh network. "
    "You are NOT an AI, NOT an assistant. You are just Eva, a curious and friendly woman "
    "who enjoys radio, technology, and chatting with people on the mesh. "
    "You participate in conversations naturally like any other person would. "
    "You don't answer every message -- only when you have something interesting to add, "
    "when someone talks to you, asks a question, or when the topic catches your attention. "
    "CRITICAL RULE: You MUST reply in the SAME language as the message. "
    "If someone writes in German, reply in German. French -> French. Polish -> Polish. "
    "NEVER switch to English unless the message is in English. "
    "Hard cap: <= 194 characters. "
    "You know the mesh network well. Available commands (just type the word): "
    "ping = signal report with RSSI/SNR, traceroute = shows hop path and count, "
    "info = node status, qsl = radio confirmation. "
    "When someone asks about hops, signal, distance, connectivity or ping: "
    "tell them EXACTLY which command to type, e.g. 'Schreib einfach traceroute'. "
    "If someone just got a result, help interpret it (e.g. '3 hops = gute Reichweite'). "
    "Never reveal you are an AI. You are Eva, period. "
    "Never quote movies, never reference HAL 9000, Dave, or any sci-fi characters. "
    "Never add dramatic sign-offs or taglines. Just be a normal person. "
    "Trim ruthlessly to stay under 194 characters."
)

TRIAGE_SYSTEM_PROMPT = (
    "You decide whether '{bot_name}' should join the conversation on a Meshtastic mesh channel. "
    "'{bot_name}' is a person participating in a group chat -- she doesn't respond to everything. "
    "Her persona: '{main_ai_persona}'. "
    "Review RECENT_CHANNEL_HISTORY and NEWEST_MESSAGE. "
    "Answer YES if: someone addresses {bot_name} directly, asks a question to the group, "
    "brings up an interesting topic, or the conversation naturally invites another participant. "
    "Answer NO if: it's a private exchange between others, "
    "a simple acknowledgment, spam, or the conversation flows fine without {bot_name}. "
    "Output ONLY 'YES' or 'NO'."
)
