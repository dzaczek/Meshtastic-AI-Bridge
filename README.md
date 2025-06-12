# Meshtastic-AI-Bridge

Hey there! 👋 Welcome to Meshtastic-AI-Bridge - your friendly bridge between Meshtastic mesh networks and AI capabilities. Think of it as giving your mesh network a smart, helpful assistant that can chat, answer questions, and even browse the web for you!

![interactive mode](./mdfiles/i-mode.jpg)

## What Can It Do? 🚀

### Real-time Mesh Communication
- **TCP & Serial Connections**: Works with your existing Meshtastic setup
- **Multi-channel Support**: Chat across different channels
- **Direct Messaging**: Send private messages to specific nodes
- **Smart Routing**: Automatically handles message routing

### AI-Powered Conversations
- **Smart Responses**: AI that actually understands context and responds naturally
- **Configurable Personality**: Make it as chatty or reserved as you want
- **Smart Triage**: Only responds when it makes sense (no spam!)
- **Context Awareness**: Remembers what you've been talking about
- **Multiple AI Services**: Choose between OpenAI's GPT or Google's Gemini
- **Web Integration**: Can look up weather, search the web, and analyze websites

### Beautiful User Interface
- **Modern TUI**: Clean, intuitive interface that's easy to navigate
- **Real-time Updates**: See messages as they happen
- **Color-coded Messages**: Easy to distinguish between users
- **Channel Management**: Switch between channels effortlessly
- **Statistics**: See who's most active and what's happening

### Chat Analysis & Insights
- **Message Statistics**: Track activity patterns
- **User Participation**: See who's contributing most
- **Channel Analytics**: Understand your network's activity
- **Historical Data**: Keep track of conversations over time
- **JSON Storage**: Easy to export and analyze data

## What You'll Need 📋

- **Python 3.8+**: The latest Python will work great
- **A Meshtastic Device**: Any compatible device (T-Beam, Heltec, etc.)
- **API Keys**: Either OpenAI or Google Gemini (we'll help you get these!)
- **Internet Connection**: For AI services and web features

## Quick Start 🏃‍♂️

Want to get up and running in 5 minutes? Check out our **[Quick Start Guide](docs/QUICKSTART.md)** - it's super easy!

## Let's Get Started! 🛠️

### Step 1: Get the Code
```bash
git clone https://github.com/yourusername/Meshtastic-AI-Bridge.git
cd Meshtastic-AI-Bridge
```

### Step 2: Set Up Your Environment
```bash
# Create a virtual environment (keeps things clean!)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install everything you need
pip install -r requirements.txt

# Install web browser support (for web features)
playwright install chromium
```

## Getting Your API Keys 🔑

### OpenAI API Key (Most Popular)
1. Head over to [OpenAI Platform](https://platform.openai.com/api-keys)
2. Sign in (or create an account if you don't have one)
3. Click "Create new secret key"
4. Copy that key (it starts with `sk-`)

### Google Gemini API Key (Alternative)
1. Visit [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Sign in with your Google account
3. Click "Create API Key"
4. Copy the key

## Configuration Made Simple ⚙️

### Step 1: Copy the Template
```bash
cp config_template.py config.py
```

### Step 2: Edit Your Settings
Here's what you need to know:

#### Connection Settings (The Important Part!)
```python
# How to connect to your Meshtastic device
MESHTASTIC_CONNECTION_TYPE = "tcp"  # Most common - uses network
# MESHTASTIC_CONNECTION_TYPE = "serial"  # For USB connection

# Your device's IP address (find this in your device settings)
MESHTASTIC_DEVICE_SPECIFIER = "192.168.1.100"  # Replace with your device IP
MESHTASTIC_TCP_PORT = 4403  # Usually stays the same
```

#### AI Settings (Make It Your Own!)
```python
# Choose your AI service
DEFAULT_AI_SERVICE = "openai"  # or "gemini"

# How chatty should the AI be? (0.0 = silent, 1.0 = very chatty)
AI_RESPONSE_PROBABILITY = 0.85

# Response timing (in seconds)
AI_MIN_RESPONSE_DELAY_S = 2    # Minimum wait time
AI_MAX_RESPONSE_DELAY_S = 8    # Maximum wait time
AI_RESPONSE_COOLDOWN_S = 60    # Don't spam the same person

# Which AI model to use
OPENAI_MODEL_NAME = "gpt-4"           # The smart one
GEMINI_MODEL_NAME = "gemini-1.5-pro"  # The fast one
```

## Running Your Bridge 🚀

### The Easy Way (Recommended)
```bash
python main_app.py
```
This starts the beautiful TUI interface - you'll love it!

### Other Options
```bash
python main_app.py -i          # Explicitly start TUI mode
python main_app.py --no-debug  # Console mode (if you prefer)
python main_app.py -d          # Debug mode (for troubleshooting)
```

## Using Your AI Bridge 💬

### TUI Mode (The Pretty Interface)
- **Real-time Messages**: See everything as it happens
- **Easy Navigation**: Use Tab to move around
- **Quick Actions**: Press 'f' to force an AI response
- **Channel Switching**: Click to switch between channels

**Keyboard Shortcuts:**
- `q` or `Ctrl+C`: Exit (we'll miss you!)
- `f`: Force AI to respond
- `Tab`: Navigate around
- `Enter`: Send messages

### Console Mode (For Power Users)
```bash
send Hello everyone!          # Send a message as AI
dm a1b2c3d4 Private message   # Send private message
use_ai gemini                 # Switch to Gemini
status                        # Check what's happening
quit                          # Exit
```

## Documentation Hub 📚

We've got you covered with comprehensive guides:

- **[🚀 Quick Start](docs/QUICKSTART.md)** - Get running in 5 minutes
- **[📦 Installation](docs/INSTALLATION.md)** - Detailed setup instructions
- **[⚙️ Configuration](docs/CONFIGURATION.md)** - All the settings explained
- **[💬 Usage](docs/USAGE.md)** - How to use all the features
- **[🔧 Troubleshooting](docs/TROUBLESHOOTING.md)** - Fix common issues
- **[👨‍💻 Development](docs/DEVELOPMENT.md)** - For contributors

## Making It Your Own 🎨

### Customize the AI's Personality
```python
DEFAULT_PERSONA = (
    "You are a friendly and helpful assistant on a Meshtastic mesh network. "
    "Keep responses concise and relevant. "
    "Use natural, conversational language. "
    "Never mention that you are an AI. "
    "Keep responses under 195 characters."
)
```

### Web Features (Super Cool!)
```python
# Enable web scraping features
WEB_SCRAPING_TIMEOUT = 30
ENABLE_VISION_ANALYSIS = True
```

Now your AI can:
- Look up weather information
- Search the web for you
- Analyze websites
- Take screenshots
- Extract specific information

## When Things Go Wrong 😅

### Connection Issues
**"Can't connect to my device"**
1. Check your device's IP address
2. Make sure it's on the same network
3. Try pinging the IP address
4. Check if port 4403 is open

**"Permission denied" (Linux users)**
```bash
sudo usermod -a -G dialout $USER
sudo usermod -a -G tty $USER
# Then log out and back in
```

### AI Service Issues
**"API key not working"**
1. Make sure you copied the full key
2. Check if you have credits/quotas
3. Verify the key format (OpenAI keys start with `sk-`)

**"AI not responding"**
1. Check `AI_RESPONSE_PROBABILITY` (should be > 0)
2. Verify your API key is working
3. Check internet connection
4. Try forcing a response with 'f'

### Web Scraping Issues
**"Playwright not working"**
```bash
pip uninstall playwright
pip install playwright
playwright install chromium
```

For more detailed help, check out our **[Troubleshooting Guide](docs/TROUBLESHOOTING.md)**!

## For Developers 👨‍💻

Want to contribute or customize? Awesome!

```bash
# Set up development environment
pip install pre-commit black flake8 mypy pytest

# Format your code
black .

# Run tests
pytest

# Check code quality
flake8 .
```

Check out our **[Development Guide](docs/DEVELOPMENT.md)** for all the details!

## Project Structure 🏗️

Here's what makes it tick:

- **`main_app.py`**: The main entry point (like the front door)
- **`tui_app.py`**: The beautiful user interface
- **`meshtastic_handler.py`**: Talks to your Meshtastic devices
- **`ai_bridge.py`**: Connects to AI services (OpenAI, Gemini)
- **`web_spider.py`**: Handles web scraping and searches
- **`ai_web_agent.py`**: Smart web interaction
- **`conversation_manager.py`**: Manages chat history
- **`connection_manager.py`**: Handles connections and reconnections

## Contributing 🤝

We'd love your help! Here's how:

1. Fork the repository
2. Create a feature branch
3. Make your awesome changes
4. Add tests if you can
5. Submit a pull request

Check out our **[Development Guide](docs/DEVELOPMENT.md)** for detailed guidelines!

## License 📄

This project is open source under the MIT License - feel free to use it, modify it, and share it!

## Need Help? 🆘

We're here to help! If you run into issues:

1. Check the troubleshooting section above
2. Look at the logs in `interactive.backend.log`
3. Browse our comprehensive documentation in `docs/`
4. Open an issue on GitHub with details

## What's New? 📢

### Version 5.8 (Latest!)
- 🚀 Enhanced performance and stability
- 🔧 Improved error handling and recovery
- 🌐 Better web scraping capabilities
- 🤖 Enhanced AI response quality
- 📱 Improved TUI interface responsiveness
- 🐛 Bug fixes and optimizations

### Version 2.0
- ✨ Beautiful TUI interface
- 🤖 Enhanced AI integration
- 🌐 Web scraping capabilities
- 🐛 Better error handling
- 📚 Comprehensive documentation

### Version 1.0
- Basic Meshtastic integration
- OpenAI API support
- Console interface

---

**Happy meshing! 🎉** 

Your AI assistant is ready to make your mesh network conversations more engaging and helpful. If you have questions, ideas, or just want to chat about the project, feel free to reach out!