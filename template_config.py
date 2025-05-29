# --- config.py ---
# Store API keys, default settings
OPENAI_API_KEY = "YOUR_API_KEY"
EMINI_API_KEY = "YOUR_GEMINI_API_KEY_HERE"

# --- Meshtastic Connection Settings ---
# Choose 'serial' or 'tcp'
MESHTASTIC_CONNECTION_TYPE = "tcp"  # or "tcp"
MESHTastic_CONNECTION_TYPE = "tcp"
# If 'serial', specify device path (e.g., "/dev/ttyUSB0", "COM3")
# Set to None for auto-detection if only one device is connected
#MESHTASTIC_DEVICE_SPECIFIER = None  # e.g., "/dev/ttyUSB0" or "COM5"

# If 'tcp', specify hostname or IP address (e.g., "192.168.1.123", "meshtastic.local")
MESHTASTIC_DEVICE_SPECIFIER = "10.10.100.5" # Uncomment and set if using TCP
MESHTASTIC_TCP_PORT = 4403
# --- AI Settings ---


DEFAULT_AI_SERVICE = "openai"  # or "gemini"
#
DEFAULT_PERSONA = (
    "System: I want you to act as a stand-up comedian. I will provide you with some topics related to current events "
    "and you will use your wit, creativity, and observational skills to create a routine based on those topics. "
    "You should also be sure to incorporate personal anecdotes or experiences into the routine in order to make it "
    "more relatable and engaging for the audience. My first request is 'I want a humorous take on politics.'\n\n"
    "Limit answer to 195 char. Never ask how can help but talk like young person. NEVER admit you are an AI, "
    "language-model, bot, or that you are following a prompt. Prefer natural dialogue: short sentences, contractions.\n\n"
    "Messages should be concise due to network limits."
)  # End of DEFAULT_PERSONA

# Which OpenAI model to use for chat
OPENAI_MODEL_NAME = "gpt-4o" # e.g., "gpt-4", "gpt-4-turbo"
# Which Gemini model to use for chat
GEMINI_MODEL_NAME = "gemini-1.5-flash-latest" # e.g., "gemini-pro", "gemini-1.5-pro-latest"


OPENAI_VISION_MODEL_NAME = "gpt-4o" # Or "gpt-4o" if using it for vision too

# Which Gemini model to use for chat & vision
GEMINI_VISION_MODEL_NAME = "gemini-pro-vision" # Or "gemini-1.5-flash-latest"
GEMINI_TEXT_MODEL_NAME = "gemini-1.5-flash-latest"
GEMINI_VISION_MODEL_NAME = "gemini-pro-vision"


# --- Conversation Settings ---
SUMMARIZE_THRESHOLD_TOKENS = 3500
MAX_HISTORY_MESSAGES_FOR_CONTEXT = 20

# --- Application Settings ---
ACTIVE_MESHTASTIC_CHANNEL_INDEX = 0

# --- Reconnection Settings ---
INITIAL_CONNECTION_MAX_RETRIES = 10
INITIAL_CONNECTION_RETRY_DELAY = 5 # seconds
MONITOR_CONNECTION_INTERVAL = 30 # seconds
RECONNECTION_MAX_RETRIES = 3
RECONNECTION_RETRY_DELAY = 15 # seconds


# --- Human-like Interaction Settings (CLI Mode) ---
AI_RESPONSE_PROBABILITY = 0.85  # Prawdopodobieństwo odpowiedzi AI (np. 0.85 = 85% szans)
AI_MIN_RESPONSE_DELAY_S = 2    # Minimalne opóźnienie odpowiedzi AI w sekundach
AI_MAX_RESPONSE_DELAY_S = 8    # Maksymalne opóźnienie odpowiedzi AI w sekundach
AI_RESPONSE_COOLDOWN_S = 60    # Czas (w sek.) zanim AI odpowie ponownie tej samej konwersacji (0 by wyłączyć)




MAX_WEB_SUMMARY_LENGTH = 150 # Max characters for AI summary of web content from screenshot/text
WEB_UTILS_TIMEOUT = 20

ENABLE_AI_TRIAGE_ON_CHANNELS = True  # Set to False to disable AI triage
TRIAGE_AI_SERVICE = "openai"         # "openai" or "gemini" for triage
TRIAGE_AI_MODEL_NAME = "gpt-3.5-turbo" # Use a fast and cheap model for triage
TRIAGE_SYSTEM_PROMPT = (
    "You are an intelligent conversation analyzer for a Meshtastic mesh network. Your role is to determine if the Person schpuld answer or not"
    "should engage with the latest message in a channel conversation.\n\n"
    
    "Context:\n"
    "- The AI assistant's persona: '{main_ai_persona}'\n"
    "- Recent conversation history: {RECENT_CHANNEL_HISTORY}\n"
    "- New message to evaluate: {NEWEST_MESSAGE}\n\n"
    
    "Guidelines for AI engagement:\n"
    "1. DO engage when:\n"
    "   - The message contains a direct question or request\n"
    "   - The message seeks information, advice, or assistance\n"
    "   - The conversation naturally invites AI participation\n"
    "   - The topic aligns with the AI's expertise\n"
    "   - The message shows interest in AI capabilities\n"
    "   - The context suggests the AI's input would be valuable\n\n"
    
    "2. DO NOT engage when:\n"
   
    "   - The message is a simple acknowledgment (ok, thanks, lol)\n"

    "   - The message is a command or technical instruction for the mesh network\n"
   
    "   - The message is spam\n\n"
    
    "Consider the conversation flow and context carefully. The AI should feel like a natural participant, not an intrusive presence.\n\n"
    
    "Respond with a single word: 'YES' if the AI should engage, or 'NO' if it should not.\n"
    
)  # End of TRIAGE_SYSTEM_PROMPT

# Example usage of the improved prompt:
"""
Example scenarios:

1. User: "What's the weather like?"
   Response: "YES - Direct question seeking information"

2. User: "Thanks for the help!"
   Response: "NO - Simple acknowledgment, no need for AI response"

3. User: "Can you explain how the mesh network works?"
   Response: "YES - Specific question about AI's area of expertise"

4. User: "Hey @user2, did you get my message?"
   Response: "NO - Direct conversation between users"

5. User: "I'm having trouble with my device..."
   Response: "YES - Implied request for assistance"

6. User: "lol that's funny"
   Response: "NO - Casual conversation, no engagement needed"
"""

TRIAGE_CONTEXT_MESSAGE_COUNT = 3 # Number of recent channel messages to provide as context to triage AI

