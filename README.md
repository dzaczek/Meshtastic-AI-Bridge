# Meshtastic AI Bridge

A powerful bridge application that connects Meshtastic mesh networks with AI capabilities, featuring a beautiful Textual-based TUI interface for real-time communication and chat analysis.

## 🌟 Key Features

### 📡 Real-time Mesh Communication
- **TCP Connection** - ✅ Fully tested and operational
- **Serial Connection** - ✅ Tested and working (USB/UART)
- **Multi-channel Support** - Monitor and respond on multiple channels
- **Direct Messaging** - Private conversations with mesh nodes

### 🤖 AI Integration
- **Smart Response System** - AI-powered automatic responses
- **Configurable Behavior** - Adjust response probability and timing
- **Message Triage** - Intelligent filtering of messages to respond to
- **Context Awareness** - Maintains conversation history and context
- **Force AI Response** - Manual trigger for AI responses (press 'f' or click button)

### 💻 Modern TUI Interface (-i mode)
- **Beautiful Terminal UI** - Built with Textual framework
- **Real-time Updates** - Live message display with auto-scrolling
- **Color-coded Messages** - Visual distinction between users
- **Keyboard Navigation** - Full keyboard shortcuts support
- **Scrollable Chat History** - Navigate through conversation history

### 📊 Analytics & Tools
- **Message Statistics** - Track messages per user and channel
- **Participation Metrics** - See user activity percentages
- **History Analysis** - Analyze stored conversations
- **JSON Storage** - All conversations saved in JSON format

## 🚀 Quick Start

### Prerequisites
- Python 3.8 or higher
- Meshtastic device (or TCP simulator)
- OpenAI API key or Gemini API key (for AI features)

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/Meshtastic-AI-Bridge.git
cd Meshtastic-AI-Bridge

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy and configure settings
cp config_template.py config.py
# Edit config.py with your settings
```

## ⚙️ Configuration

Edit `config.py` with your settings:

```python
# Connection settings (choose one)
MESHTASTIC_CONNECTION_TYPE = "tcp"     # For network connection
# MESHTASTIC_CONNECTION_TYPE = "serial" # For USB/serial connection

# For TCP:
MESHTASTIC_DEVICE_SPECIFIER = "localhost:4403"

# For Serial (tested):
# MESHTASTIC_DEVICE_SPECIFIER = "/dev/ttyUSB0"  # Linux
# MESHTASTIC_DEVICE_SPECIFIER = "/dev/tty.usbserial-0001"  # macOS
# MESHTASTIC_DEVICE_SPECIFIER = "COM3"  # Windows

# AI Configuration
DEFAULT_AI_SERVICE = "openai"  # or "gemini"
OPENAI_API_KEY = "your-api-key-here"
GEMINI_API_KEY = "your-api-key-here"

# AI Behavior
AI_RESPONSE_PROBABILITY = 0.85  # 85% chance to respond
AI_MIN_RESPONSE_DELAY_S = 2
AI_MAX_RESPONSE_DELAY_S = 8
AI_RESPONSE_COOLDOWN_S = 60

# Triage settings (for channel messages)
ENABLE_AI_TRIAGE_ON_CHANNELS = False  # Enable smart filtering
TRIAGE_CONTEXT_MESSAGE_COUNT = 3      # Messages to analyze
```

## 📖 Usage Guide

### Running the Application

```bash
# Interactive TUI mode (recommended)
python main_app.py -i

# Console mode (legacy)
python main_app.py

# With debug output
python main_app.py -i -d

# Disable debug prints
python main_app.py -i --no-debug-prints
```

### TUI Mode Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `q` | Quit application |
| `Tab` | Focus next panel |
| `Shift+Tab` | Focus previous panel |
| `m` | Focus chat messages |
| `c` | Focus channel list |
| `n` | Focus node list |
| `f` | Force AI response |
| `↑/↓` | Scroll messages |
| `Page Up/Down` | Scroll page |
| `Home/End` | Jump to top/bottom |

### Chat Analysis Tool

```bash
cd conversations
python chat_ui.py
```

## 🤖 AI Features Explained

### Force AI Response
You can manually trigger an AI response at any time:
- **Keyboard**: Press `f` key in TUI mode
- **Button**: Click "🤖 Force AI" button
- **Use Cases**:
  - Make AI respond when it normally wouldn't
  - Generate AI commentary on quiet channels
  - Test AI responses without waiting

### AI Triage System
The triage system intelligently filters which messages the AI should respond to:

1. **How it works**:
   - Analyzes the last N messages (configurable)
   - Determines if the conversation needs AI input
   - Prevents AI from responding to every message
   - Reduces spam and improves conversation quality

2. **Triage is bypassed for**:
   - Direct messages to the AI node
   - Forced AI responses (using 'f' key)
   - When `ENABLE_AI_TRIAGE_ON_CHANNELS` is False

3. **Configuration**:
   ```python
   # Enable/disable triage for channel messages
   ENABLE_AI_TRIAGE_ON_CHANNELS = True
   
   # Number of recent messages to analyze
   TRIAGE_CONTEXT_MESSAGE_COUNT = 3
   ```

## 📁 Project Structure

```
mesh5.7_dev/
├── main_app.py              # Main entry point
├── tui_app.py              # TUI interface implementation
├── meshtastic_handler.py   # Meshtastic device communication
├── ai_bridge.py           # AI service integration
├── conversation_manager.py # Chat history management
├── web_utils.py           # URL content analysis
├── config.py              # Your configuration (create from template)
├── config_template.py     # Configuration template
├── requirements.txt       # Python dependencies
├── meshtastic_tui.css    # TUI styling
├── conversations/         # Stored conversations
│   ├── chat_ui.py        # Analysis tool
│   └── *.json           # JSON chat logs
└── tui.backend.log       # Debug log file
```

## 🔧 Connection Types

### TCP Connection ✅
- Connect via network to Meshtastic device
- Default port: 4403
- Useful for remote devices or simulators
- Example: `localhost:4403`, `192.168.1.100:4403`

### Serial Connection ✅
- Direct USB/UART connection
- Tested on Linux, macOS, and Windows
- Auto-detects device settings
- Examples:
  - Linux: `/dev/ttyUSB0`, `/dev/ttyACM0`
  - macOS: `/dev/tty.usbserial-0001`
  - Windows: `COM3`, `COM4`

## 🐛 Troubleshooting

### Common Issues

1. **Connection Failed**
   - Check device is connected: `ls /dev/tty*` (Linux/macOS) or Device Manager (Windows)
   - Ensure correct permissions: `sudo chmod 666 /dev/ttyUSB0`
   - Verify device not in use by another program

2. **TUI Display Issues**
   - Try different terminal emulators
   - Adjust terminal font size for better scrolling
   - Use `-i` flag for interactive mode

3. **AI Not Responding**
   - Check API keys in config.py
   - Verify internet connection
   - Check AI response probability settings

## 📝 TODO / Roadmap

### Testing & Development
- [ ] **Unit Tests** - Comprehensive test suite for all modules
- [ ] **No-Device Test Environment** - Mock Meshtastic device for development
- [ ] **CI/CD Pipeline** - Automated testing and deployment
- [ ] **Docker Container** - Easy deployment solution

### Features
- [ ] **Multi-AI Support** - Claude, Llama, local models
- [ ] **Voice Messages** - Audio message support
- [ ] **Message Encryption** - End-to-end encryption
- [ ] **Web Interface** - Browser-based UI
- [ ] **Mobile App** - iOS/Android companion
- [ ] **Plugin System** - Extensible architecture

### Improvements
- [ ] **Better Error Handling** - Graceful failure recovery
- [ ] **Performance Optimization** - Faster message processing
- [ ] **Database Storage** - SQLite instead of JSON
- [ ] **Message Search** - Full-text search in history
- [ ] **Export Functions** - CSV, PDF reports

## 🤝 Contributing

We welcome contributions! Please see our contributing guidelines:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- [Meshtastic](https://meshtastic.org/) - The amazing mesh networking project
- [Textual](https://github.com/Textualize/textual) - Beautiful TUI framework
- [Rich](https://github.com/Textualize/rich) - Terminal formatting library
- Community contributors and testers

## 💬 Support

- **Issues**: Use the [GitHub issue tracker](https://github.com/yourusername/Meshtastic-AI-Bridge/issues)
- **Discussions**: Join our [Discord server](https://discord.gg/your-invite)
- **Wiki**: Check our [documentation wiki](https://github.com/yourusername/Meshtastic-AI-Bridge/wiki)

---

Made with ❤️ by the Meshtastic community 