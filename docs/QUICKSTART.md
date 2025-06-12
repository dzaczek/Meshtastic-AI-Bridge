# Quick Start Guide

Get up and running with Meshtastic-AI-Bridge in 5 minutes!

## Prerequisites

- Python 3.8 or higher
- A Meshtastic device (T-Beam, Heltec, etc.)
- OpenAI API key or Google Gemini API key

## Step 1: Install the Application

```bash
# Clone the repository
git clone https://github.com/yourusername/Meshtastic-AI-Bridge.git
cd Meshtastic-AI-Bridge

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
playwright install chromium
```

## Step 2: Get API Keys

### OpenAI API Key
1. Go to [OpenAI Platform](https://platform.openai.com/api-keys)
2. Sign in and click "Create new secret key"
3. Copy the key (starts with `sk-`)

### Google Gemini API Key (Alternative)
1. Go to [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Sign in and click "Create API Key"
3. Copy the key

## Step 3: Configure the Application

```bash
# Copy configuration template
cp config_template.py config.py

# Edit configuration (use your preferred editor)
nano config.py
```

### Basic Configuration

```python
# Add your API key (choose one)
OPENAI_API_KEY = "sk-your-actual-api-key-here"
# GEMINI_API_KEY = "your-gemini-api-key-here"

# Configure Meshtastic connection
MESHTASTIC_CONNECTION_TYPE = "tcp"  # or "serial"
MESHTASTIC_DEVICE_SPECIFIER = "192.168.1.100"  # Your device IP
MESHTASTIC_TCP_PORT = 4403

# Choose AI service
DEFAULT_AI_SERVICE = "openai"  # or "gemini"
```

## Step 4: Find Your Meshtastic Device IP

### Method 1: Check Device Settings
1. Connect to your Meshtastic device
2. Check the device settings for IP address
3. Note the IP address (e.g., 192.168.1.100)

### Method 2: Network Scan
```bash
# Scan your network for Meshtastic devices
nmap -p 4403 192.168.1.0/24
```

### Method 3: Router Admin Panel
1. Log into your router's admin panel
2. Check connected devices
3. Look for your Meshtastic device

## Step 5: Run the Application

```bash
# Start the application
python main_app.py
```

You should see:
- Connection status messages
- TUI interface loading
- Ready to receive messages

## Step 6: Test the Setup

### Send a Test Message
1. From another Meshtastic device, send a message
2. You should see the message appear in the interface
3. The AI should respond automatically

### Manual Test
1. Press `f` to force an AI response
2. Type a message and press Enter
3. Check if the AI responds

## Troubleshooting Quick Fixes

### Connection Issues
```bash
# Test if device is reachable
ping 192.168.1.100  # Replace with your device IP

# Check if port is open
telnet 192.168.1.100 4403
```

### API Key Issues
```python
# In config.py, make sure your key is correct
OPENAI_API_KEY = "sk-your-actual-key"  # Not placeholder text
```

### Permission Issues (Linux)
```bash
# Fix serial port permissions
sudo chmod 666 /dev/ttyUSB0
```

## Common Configuration Examples

### TCP Connection (Most Common)
```python
MESHTASTIC_CONNECTION_TYPE = "tcp"
MESHTASTIC_DEVICE_SPECIFIER = "192.168.1.100"
MESHTASTIC_TCP_PORT = 4403
```

### Serial Connection (USB)
```python
MESHTASTIC_CONNECTION_TYPE = "serial"
MESHTASTIC_DEVICE_SPECIFIER = "/dev/ttyUSB0"  # Linux
# MESHTASTIC_DEVICE_SPECIFIER = "COM3"        # Windows
```

### High AI Activity
```python
AI_RESPONSE_PROBABILITY = 0.9
AI_MIN_RESPONSE_DELAY_S = 1
AI_MAX_RESPONSE_DELAY_S = 3
```

### Low AI Activity
```python
AI_RESPONSE_PROBABILITY = 0.3
AI_MIN_RESPONSE_DELAY_S = 5
AI_MAX_RESPONSE_DELAY_S = 15
```

## Next Steps

Once you're up and running:

1. **Customize AI Persona**: Edit `DEFAULT_PERSONA` in `config.py`
2. **Adjust Response Settings**: Modify AI response probability and timing
3. **Explore Features**: Try web search, weather queries, and URL analysis
4. **Read Full Documentation**: Check the other guides in the `docs/` folder

## Getting Help

If you encounter issues:

1. **Check Logs**: Look at `interactive.backend.log`
2. **Verify Configuration**: Ensure all settings are correct
3. **Test Components**: Use the troubleshooting commands above
4. **Ask for Help**: Open an issue on GitHub with your error details

## Quick Commands Reference

### Application Control
```bash
python main_app.py              # Start TUI mode
python main_app.py -d           # Start with debug logging
python main_app.py --no-debug   # Start console mode
```

### TUI Shortcuts
- `q` or `Ctrl+C`: Quit
- `f`: Force AI response
- `Tab`: Navigate interface
- `Enter`: Send message

### Console Commands
```bash
send <message>          # Send message as AI
status                  # Show current status
use_ai <openai|gemini>  # Switch AI service
quit                    # Exit application
```

## Success Indicators

You know it's working when:

✅ **Connection**: "Meshtastic handler connected" message appears  
✅ **AI Service**: "OpenAI client initialized" or "Gemini configured"  
✅ **Interface**: TUI loads without errors  
✅ **Messages**: Incoming messages appear in the interface  
✅ **AI Responses**: AI responds to messages automatically  

## Performance Tips

### For Better Performance
```python
# Use faster models
OPENAI_MODEL_NAME = "gpt-3.5-turbo"  # Instead of gpt-4
GEMINI_MODEL_NAME = "gemini-1.5-flash-latest"

# Reduce context window
MAX_HISTORY_MESSAGES_FOR_CONTEXT = 5
```

### For Lower Costs
```python
# Reduce AI activity
AI_RESPONSE_PROBABILITY = 0.5
AI_RESPONSE_COOLDOWN_S = 120
```

## Security Notes

- Never commit `config.py` to version control
- Keep your API keys secure
- Use environment variables in production
- Regularly rotate API keys

## What's Next?

After successful setup:

1. **Read the [Usage Guide](USAGE.md)** for detailed instructions
2. **Check the [Configuration Guide](CONFIGURATION.md)** for advanced settings
3. **Review the [Troubleshooting Guide](TROUBLESHOOTING.md)** for common issues
4. **Join the community** for support and discussions

Congratulations! You're now ready to use Meshtastic-AI-Bridge! 🎉 