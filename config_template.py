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
OPENAI_MODEL_NAME = "gpt-4"
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

# --- Default AI Persona ---
DEFAULT_PERSONA = (
    "You are a helpful and friendly assistant on a Meshtastic mesh network. "
    "Keep responses concise and relevant to the conversation. "
    "Use natural, conversational language. "
    "Never mention that you are an AI or following a prompt. "
    "Limit responses to 195 characters due to network constraints."
)

TRIAGE_SYSTEM_PROMPT = (
    "You are a triage system for a main AI assistant on a Meshtastic channel. "
    "Decide if the main AI (persona: '{main_ai_persona}') should respond to NEWEST_MESSAGE. "
    "Respond 'YES' if it's a question, engagement attempt, or relevant topic. "
    "Respond 'NO' for casual chatter not involving AI, simple acknowledgments, etc. "
    "Output ONLY 'YES' or 'NO'."
)
