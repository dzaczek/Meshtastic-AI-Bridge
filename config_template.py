# --- config.py ---
# Store API keys, default settings
OPENAI_API_KEY = "YOUR_API_KEY"
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY_HERE"

# --- Meshtastic Connection Settings ---
# Choose 'serial' or 'tcp'
MESHTASTIC_CONNECTION_TYPE = "serial"  # Use "serial" for USB connection, "tcp" for network connection

# For serial connection (USB):
# Set to None for auto-detection, or specify the device path
MESHTASTIC_DEVICE_SPECIFIER = None  # e.g., "/dev/ttyUSB0" or "COM5" or None for auto-detect

# For TCP connection:
# MESHTASTIC_DEVICE_SPECIFIER = "192.168.1.123"  # Hostname or IP address
# MESHTASTIC_TCP_PORT = 4403  # Default Meshtastic TCP port

# Active channel for AI responses (0 is usually the default channel)
ACTIVE_MESHTASTIC_CHANNEL_INDEX = 0

# --- AI Settings ---
DEFAULT_AI_SERVICE = "openai"  # or "gemini"

# AI Response Settings
AI_RESPONSE_PROBABILITY = 0.85  # Probability of AI responding to messages
AI_MIN_RESPONSE_DELAY_S = 2    # Minimum delay before AI responds
AI_MAX_RESPONSE_DELAY_S = 8    # Maximum delay before AI responds
AI_RESPONSE_COOLDOWN_S = 60    # Cooldown period between AI responses to the same user

# AI Triage Settings
ENABLE_AI_TRIAGE_ON_CHANNELS = False  # Enable AI responses on all channels
TRIAGE_CONTEXT_MESSAGE_COUNT = 3      # Number of messages to include in context

# Conversation History Settings
MAX_HISTORY_MESSAGES_FOR_CONTEXT = 10  # Maximum number of messages to keep in context
SUMMARIZE_THRESHOLD_TOKENS = 1000      # Threshold for summarizing conversation history

# --- Model Settings ---
# OpenAI Models
OPENAI_MODEL_NAME = "gpt-4"  # e.g., "gpt-4", "gpt-4-turbo"
OPENAI_VISION_MODEL_NAME = "gpt-4-vision-preview"  # For vision tasks

# Gemini Models
GEMINI_MODEL_NAME = "gemini-1.5-pro"  # e.g., "gemini-pro", "gemini-1.5-pro"
GEMINI_VISION_MODEL_NAME = "gemini-pro-vision"  # For vision tasks

# --- Default AI Persona ---
DEFAULT_PERSONA = (
    "You are a helpful and friendly assistant on a Meshtastic mesh network. "
    "Keep responses concise and relevant to the conversation. "
    "Use natural, conversational language. "
    "Never mention that you are an AI or following a prompt. "
    "Limit responses to 195 characters due to network constraints."
) 