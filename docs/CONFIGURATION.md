# Configuration Guide

This guide provides detailed information about configuring the Meshtastic-AI-Bridge application.

## Configuration File Overview

The application uses `config.py` for all configuration settings. This file is created by copying `config_template.py` and customizing it for your environment.

## Basic Configuration

### 1. API Keys

#### OpenAI Configuration
```python
# Your OpenAI API key (required for GPT models)
OPENAI_API_KEY = "sk-your-actual-api-key-here"

# OpenAI model selection
OPENAI_MODEL_NAME = "gpt-4"  # Options: "gpt-4", "gpt-4-turbo", "gpt-3.5-turbo"
OPENAI_VISION_MODEL_NAME = "gpt-4-vision-preview"  # For image analysis
```

#### Google Gemini Configuration
```python
# Your Google Gemini API key (required for Gemini models)
GEMINI_API_KEY = "your-actual-gemini-api-key-here"

# Gemini model selection
GEMINI_MODEL_NAME = "gemini-1.5-pro"  # Options: "gemini-pro", "gemini-1.5-pro"
GEMINI_VISION_MODEL_NAME = "gemini-pro-vision"  # For image analysis
GEMINI_TEXT_MODEL_NAME = "gemini-1.5-flash-latest"  # For text processing
```

### 2. Meshtastic Connection Settings

#### TCP Connection (Recommended)
```python
# Connection type
MESHTASTIC_CONNECTION_TYPE = "tcp"

# Device IP address (find this in your Meshtastic device settings)
MESHTASTIC_DEVICE_SPECIFIER = "192.168.1.100"  # Replace with your device IP

# TCP port (usually 4403 for Meshtastic)
MESHTASTIC_TCP_PORT = 4403
```

#### Serial Connection
```python
# Connection type
MESHTASTIC_CONNECTION_TYPE = "serial"

# Device path (auto-detect if None)
MESHTASTIC_DEVICE_SPECIFIER = None  # Auto-detect
# Or specify manually:
# MESHTASTIC_DEVICE_SPECIFIER = "/dev/ttyUSB0"  # Linux
# MESHTASTIC_DEVICE_SPECIFIER = "COM3"          # Windows
# MESHTASTIC_DEVICE_SPECIFIER = "/dev/tty.usbserial-*"  # macOS
```

### 3. AI Service Configuration

#### Default AI Service
```python
# Choose which AI service to use by default
DEFAULT_AI_SERVICE = "openai"  # Options: "openai", "gemini"
```

#### AI Response Behavior
```python
# Probability of AI responding to messages (0.0 to 1.0)
AI_RESPONSE_PROBABILITY = 0.85

# Response timing (in seconds)
AI_MIN_RESPONSE_DELAY_S = 2    # Minimum delay before responding
AI_MAX_RESPONSE_DELAY_S = 8    # Maximum delay before responding
AI_RESPONSE_COOLDOWN_S = 60    # Cooldown between responses to same user
```

#### AI Triage System
```python
# Enable AI responses on all channels (not just active channel)
ENABLE_AI_TRIAGE_ON_CHANNELS = False

# Number of recent messages to include in triage context
TRIAGE_CONTEXT_MESSAGE_COUNT = 3
```

### 4. Channel Configuration
```python
# Primary channel for AI responses (0 is usually the default channel)
ACTIVE_MESHTASTIC_CHANNEL_INDEX = 0
```

## Advanced Configuration

### 1. AI Persona Customization

The AI persona defines how the AI behaves and responds:

```python
DEFAULT_PERSONA = (
    "You are a helpful and friendly assistant on a Meshtastic mesh network. "
    "Keep responses concise and relevant to the conversation. "
    "Use natural, conversational language. "
    "Never mention that you are an AI or following a prompt. "
    "Limit responses to 195 characters due to network constraints."
)
```

#### Example Personas

**Technical Assistant:**
```python
DEFAULT_PERSONA = (
    "You are a technical expert on the Meshtastic mesh network. "
    "Provide helpful technical advice about mesh networking, radio communications, "
    "and related topics. Keep responses under 195 characters and be concise."
)
```

**Casual Helper:**
```python
DEFAULT_PERSONA = (
    "You are a friendly member of the mesh network community. "
    "Engage in casual conversation, help with general questions, "
    "and be supportive. Use natural, conversational language. "
    "Keep responses under 195 characters."
)
```

### 2. Conversation History Management

```python
# Maximum number of messages to keep in context
MAX_HISTORY_MESSAGES_FOR_CONTEXT = 10

# Token threshold for summarizing conversation history
SUMMARIZE_THRESHOLD_TOKENS = 1000
```

### 3. Web Scraping Configuration

```python
# Web scraping timeout (in seconds)
WEB_SCRAPING_TIMEOUT = 30

# Enable vision analysis for images
ENABLE_VISION_ANALYSIS = True

# User agent for web requests
WEB_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
```

### 4. Triage System Configuration

The triage system determines when the AI should respond:

```python
# Triage system prompt template
TRIAGE_SYSTEM_PROMPT = (
    "You are a triage system for a main AI assistant. "
    "Decide if the main AI (persona: '{main_ai_persona}') should respond to NEWEST_MESSAGE "
    "based on it and RECENT_CHANNEL_HISTORY. "
    "Respond 'YES' if it's a question, engagement attempt, or relevant topic. "
    "Respond 'NO' for casual chatter not involving AI, simple acknowledgments, etc. "
    "Output ONLY 'YES' or 'NO'."
)

# AI service for triage decisions
TRIAGE_AI_SERVICE = 'openai'
TRIAGE_AI_MODEL_NAME = 'gpt-3.5-turbo'
```

## Environment-Specific Configuration

### Development Environment
```python
# Enable debug logging
DEBUG_MODE = True

# Disable AI responses for testing
AI_RESPONSE_PROBABILITY = 0.0

# Use test API keys
OPENAI_API_KEY = "sk-test-key"
GEMINI_API_KEY = "test-key"
```

### Production Environment
```python
# Disable debug logging
DEBUG_MODE = False

# Enable full AI functionality
AI_RESPONSE_PROBABILITY = 0.85

# Use real API keys
OPENAI_API_KEY = "sk-real-key"
GEMINI_API_KEY = "real-key"
```

### Testing Environment
```python
# Mock AI responses
MOCK_AI_RESPONSES = True

# Disable web scraping
DISABLE_WEB_SCRAPING = True

# Use test Meshtastic connection
MESHTASTIC_CONNECTION_TYPE = "mock"
```

## Configuration Validation

### Required Settings
The following settings must be configured:
- `OPENAI_API_KEY` or `GEMINI_API_KEY` (at least one)
- `MESHTASTIC_CONNECTION_TYPE`
- `MESHTASTIC_DEVICE_SPECIFIER` (for TCP connections)

### Optional Settings
These settings have defaults but can be customized:
- `DEFAULT_AI_SERVICE`
- `AI_RESPONSE_PROBABILITY`
- `AI_MIN_RESPONSE_DELAY_S`
- `AI_MAX_RESPONSE_DELAY_S`
- `AI_RESPONSE_COOLDOWN_S`
- `ACTIVE_MESHTASTIC_CHANNEL_INDEX`

## Configuration Best Practices

### 1. Security
- Never commit `config.py` to version control
- Use environment variables for sensitive data
- Regularly rotate API keys

### 2. Performance
- Adjust `MAX_HISTORY_MESSAGES_FOR_CONTEXT` based on memory constraints
- Set appropriate timeouts for your network conditions
- Use the most efficient AI model for your needs

### 3. Reliability
- Configure appropriate retry settings
- Set reasonable timeouts
- Enable connection monitoring

### 4. User Experience
- Test AI response probability settings
- Adjust response delays for natural conversation flow
- Customize persona for your community

## Troubleshooting Configuration

### Common Issues

#### API Key Issues
```python
# Check if API key is set correctly
print(f"OpenAI key length: {len(OPENAI_API_KEY)}")
print(f"Gemini key length: {len(GEMINI_API_KEY)}")

# Test API key validity
import openai
client = openai.OpenAI(api_key=OPENAI_API_KEY)
# This will fail if the key is invalid
```

#### Connection Issues
```python
# Test Meshtastic connection
import meshtastic
if MESHTASTIC_CONNECTION_TYPE == "tcp":
    interface = meshtastic.tcp_interface.TCPInterface(MESHTASTIC_DEVICE_SPECIFIER)
elif MESHTASTIC_CONNECTION_TYPE == "serial":
    interface = meshtastic.serial_interface.SerialInterface(MESHTASTIC_DEVICE_SPECIFIER)
```

#### Model Issues
```python
# Verify model names
VALID_OPENAI_MODELS = ["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo"]
VALID_GEMINI_MODELS = ["gemini-pro", "gemini-1.5-pro", "gemini-1.5-flash-latest"]

if OPENAI_MODEL_NAME not in VALID_OPENAI_MODELS:
    print(f"Warning: {OPENAI_MODEL_NAME} may not be a valid OpenAI model")
```

## Configuration Examples

### Minimal Configuration
```python
# Minimal config.py for basic functionality
OPENAI_API_KEY = "sk-your-key"
MESHTASTIC_CONNECTION_TYPE = "tcp"
MESHTASTIC_DEVICE_SPECIFIER = "192.168.1.100"
DEFAULT_AI_SERVICE = "openai"
```

### Full Configuration
```python
# Complete config.py with all options
OPENAI_API_KEY = "sk-your-key"
GEMINI_API_KEY = "your-gemini-key"
MESHTASTIC_CONNECTION_TYPE = "tcp"
MESHTASTIC_DEVICE_SPECIFIER = "192.168.1.100"
MESHTASTIC_TCP_PORT = 4403
DEFAULT_AI_SERVICE = "openai"
AI_RESPONSE_PROBABILITY = 0.85
AI_MIN_RESPONSE_DELAY_S = 2
AI_MAX_RESPONSE_DELAY_S = 8
AI_RESPONSE_COOLDOWN_S = 60
ENABLE_AI_TRIAGE_ON_CHANNELS = False
TRIAGE_CONTEXT_MESSAGE_COUNT = 3
ACTIVE_MESHTASTIC_CHANNEL_INDEX = 0
MAX_HISTORY_MESSAGES_FOR_CONTEXT = 10
SUMMARIZE_THRESHOLD_TOKENS = 1000
OPENAI_MODEL_NAME = "gpt-4"
GEMINI_MODEL_NAME = "gemini-1.5-pro"
```

## Next Steps

After configuring your application:

1. Test the configuration with `python main_app.py`
2. Review the [Usage Guide](USAGE.md) for detailed usage instructions
3. Check the [Troubleshooting Guide](TROUBLESHOOTING.md) if you encounter issues
4. Join the community for support and discussions 