# Quick Start Guide 🚀

Hey there! Ready to give your Meshtastic network a brain? Let's get you up and running with Meshtastic-AI-Bridge v5.8 in just 5 minutes! 

## What You'll Need 📋

- **Python 3.8+**: The latest Python will work great
- **A Meshtastic Device**: Any compatible device (T-Beam, Heltec, etc.)
- **API Key**: Either OpenAI or Google Gemini (we'll help you get one!)
- **5 Minutes**: That's it! Promise! ⏱️

## Step 1: Get the Code 📥

```bash
# Clone the repository
git clone https://github.com/yourusername/Meshtastic-AI-Bridge.git
cd Meshtastic-AI-Bridge

# Create a virtual environment (keeps things clean!)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install everything you need
pip install -r requirements.txt
playwright install chromium
```

## Step 2: Get Your API Key 🔑

### Option A: OpenAI (Most Popular)
1. Go to [OpenAI Platform](https://platform.openai.com/api-keys)
2. Sign in (or create an account)
3. Click "Create new secret key"
4. Copy the key (it starts with `sk-`)

### Option B: Google Gemini (Alternative)
1. Visit [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Sign in with your Google account
3. Click "Create API Key"
4. Copy the key

## Step 3: Configure Your Bridge ⚙️

```bash
# Copy the configuration template
cp config_template.py config.py

# Edit with your favorite editor
nano config.py  # or use VS Code, vim, etc.
```

### The Essential Settings

```python
# Add your API key (choose one!)
OPENAI_API_KEY = "sk-your-actual-api-key-here"
# GEMINI_API_KEY = "your-gemini-api-key-here"

# How to connect to your device
MESHTASTIC_CONNECTION_TYPE = "tcp"  # Most common
MESHTASTIC_DEVICE_SPECIFIER = "192.168.1.100"  # Your device IP
MESHTASTIC_TCP_PORT = 4403

# Choose your AI service
DEFAULT_AI_SERVICE = "openai"  # or "gemini"
```

## Step 4: Find Your Device IP 🔍

### Method 1: Check Device Settings
1. Connect to your Meshtastic device
2. Look for the IP address in settings
3. Note it down (e.g., 192.168.1.100)

### Method 2: Network Scan (Quick!)
```bash
# Scan your network for Meshtastic devices
nmap -p 4403 192.168.1.0/24
```

### Method 3: Router Admin
1. Log into your router (usually 192.168.1.1)
2. Check "Connected Devices"
3. Find your Meshtastic device

## Step 5: Launch Your AI Bridge! 🚀

```bash
# Start the application
python main_app.py
```

You should see:
- ✅ Connection status messages
- ✅ TUI interface loading
- ✅ Ready to receive messages

## Step 6: Test It Out! 🧪

### Send a Test Message
1. From another Meshtastic device, send any message
2. Watch it appear in your interface
3. The AI should respond automatically! 🤖

### Manual Test
1. Press `f` to force an AI response
2. Type a message and press Enter
3. Check if the AI responds

## Quick Fixes for Common Issues 🔧

### "Can't connect to device"
```bash
# Test if device is reachable
ping 192.168.1.100  # Replace with your device IP

# Check if port is open
telnet 192.168.1.100 4403
```

### "API key not working"
```python
# Make sure your key is correct (not placeholder text)
OPENAI_API_KEY = "sk-your-actual-key"  # Not "sk-YOUR_API_KEY"
```

### "Permission denied" (Linux users)
```bash
# Fix serial port permissions
sudo chmod 666 /dev/ttyUSB0
```

## Popular Configuration Examples 📝

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

### Chatty AI (High Activity)
```python
AI_RESPONSE_PROBABILITY = 0.9
AI_MIN_RESPONSE_DELAY_S = 1
AI_MAX_RESPONSE_DELAY_S = 3
```

### Reserved AI (Low Activity)
```python
AI_RESPONSE_PROBABILITY = 0.3
AI_MIN_RESPONSE_DELAY_S = 5
AI_MAX_RESPONSE_DELAY_S = 15
```

## What's Next? 🎯

Once you're up and running:

1. **🎨 Customize AI Persona**: Edit `DEFAULT_PERSONA` in `config.py`
2. **⚙️ Adjust Settings**: Modify AI response probability and timing
3. **🌐 Explore Features**: Try web search, weather queries, URL analysis
4. **📚 Read More**: Check out the other guides in the `docs/` folder

## Need Help? 🆘

If something's not working:

1. **📋 Check Logs**: Look at `interactive.backend.log`
2. **🔍 Verify Config**: Make sure all settings are correct
3. **🧪 Test Components**: Use the troubleshooting commands above
4. **💬 Ask for Help**: Open an issue on GitHub with your error details

## Quick Commands Reference ⚡

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

## Success Checklist ✅

You know it's working when you see:

✅ **Connection**: "Meshtastic handler connected" message  
✅ **AI Service**: "OpenAI client initialized" or "Gemini configured"  
✅ **Interface**: TUI loads without errors  
✅ **Messages**: Incoming messages appear in the interface  
✅ **AI Responses**: AI responds to messages automatically  

## Performance Tips 💡

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

## Security Notes 🔒

- Never commit `config.py` to version control
- Keep your API keys secure
- Use environment variables in production
- Regularly rotate API keys

## What's Next? 🎉

After successful setup:

1. **📖 Read the [Usage Guide](USAGE.md)** for detailed instructions
2. **⚙️ Check the [Configuration Guide](CONFIGURATION.md)** for advanced settings
3. **🔧 Review the [Troubleshooting Guide](TROUBLESHOOTING.md)** for common issues
4. **💬 Join the community** for support and discussions

---

**🎉 Congratulations! You're now ready to use Meshtastic-AI-Bridge!**

Your AI assistant is ready to make your mesh network conversations more engaging and helpful. If you have questions, ideas, or just want to chat about the project, feel free to reach out!

Happy meshing! 🚀 