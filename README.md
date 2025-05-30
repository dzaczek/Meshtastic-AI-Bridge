# Meshtastic-AI-Bridge

A modern bridge application that connects Meshtastic mesh networks with AI capabilities, featuring a beautiful Textual-based TUI interface for chat analysis and real-time communication.

## Features

- **Real-time Mesh Communication**
  - TCP connection support (tested)
  - Serial connection support (planned)
  - Multi-channel support
  - Direct messaging capabilities

- **AI Integration**
  - AI-powered responses to messages
  - Configurable AI response probability
  - Smart message triage system
  - Context-aware conversations

- **Modern TUI Interface**
  - Beautiful Textual-based user interface
  - Real-time message display
  - Color-coded user messages
  - Channel and user statistics
  - Message history analysis

- **Chat Analysis Tools**
  - Message statistics per user and channel
  - User participation percentages
  - Channel activity metrics
  - Historical data visualization
  - JSON-based chat history storage

## Requirements

- Python 3.8 or higher
- Meshtastic device or connection
- Required Python packages (see Installation)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/Meshtastic-AI-Bridge.git
cd Meshtastic-AI-Bridge
```

2. Create and activate a virtual environment (recommended):
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install required packages:
```bash
pip install -r requirements.txt
```

## Configuration

1. Copy the configuration template:
```bash
cp config_template.py config.py
```

2. Edit `config.py` with your settings:
```python
# Connection settings
MESHTASTIC_CONNECTION_TYPE = "tcp"  # or "serial" (when implemented)
MESHTASTIC_DEVICE_SPECIFIER = "192.168.1.257"  # for TCP
MESHTASTIC_TCP_PORT = 4403                     # fort TCp

# MESHTASTIC_DEVICE_SPECIFIER = "/dev/ttyUSB0"  # for Serial

# AI settings
AI_RESPONSE_PROBABILITY = 0.85
AI_MIN_RESPONSE_DELAY_S = 2
AI_MAX_RESPONSE_DELAY_S = 8
AI_RESPONSE_COOLDOWN_S = 60
ENABLE_AI_TRIAGE_ON_CHANNELS = False
TRIAGE_CONTEXT_MESSAGE_COUNT = 3

# Channel settings
ACTIVE_MESHTASTIC_CHANNEL_INDEX = 0  # Primary channel
```

## Usage

### Running the Main Application

1. Start the application with TUI mode:
```bash
python main_app.py --textual_ui
```

2. Start in console mode:
```bash
python main_app.py
```

### Chat Analysis Tool

To analyze chat history:
```bash
cd conversations
python chat_ui.py
```

The chat analysis tool provides:
- List of available chat history files
- Message statistics per user
- Channel participation metrics
- Color-coded message display
- Interactive navigation

### Key Bindings

#### Main Application
- `q` - Quit application
- `tab` - Focus next element
- `shift+tab` - Focus previous element
- `c` - Toggle channel list
- `n` - Toggle node list

#### Chat Analysis Tool
- `q` - Quit
- `r` - Refresh view
- `f` - Focus file list
- `m` - Focus messages
- `s` - Focus statistics

## Project Structure

```
Meshtastic-AI-Bridge/
├── main_app.py              # Main application entry point
├── tui_app.py              # Textual TUI implementation
├── meshtastic_handler.py   # Meshtastic connection handling
├── ai_bridge.py           # AI integration
├── conversation_manager.py # Chat history management
├── config.py              # Configuration file
├── config_template.py     # Configuration template
├── requirements.txt       # Python dependencies
├── conversations/         # Chat history and analysis
│   ├── chat_ui.py        # Chat analysis tool
│   └── *.json           # Chat history files
└── README.md             # This file
```

## Connection Types

### TCP Connection (Tested)
- Supports connection to Meshtastic devices via TCP
- Default port: 4403
- Example: `localhost:4403`

### Serial Connection (Planned)
- Future support for direct serial connection
- Will support USB and other serial interfaces
- Configuration via device path (e.g., `/dev/ttyUSB0`)

## Contributing
_At the moment, I don't have time to check the code, so we need automated unit tests and less vibework._

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- [Meshtastic](https://meshtastic.org/) for the mesh networking protocol
- [Textual](https://github.com/Textualize/textual) for the TUI framework
- [Rich](https://github.com/Textualize/rich) for beautiful terminal formatting

## Support

For issues and feature requests, please use the GitHub issue tracker.

## Roadmap

- [ ] Serial connection support
   - [X] Tested on LilyGo T-Beam SUPREME 
- [ ] Enhanced AI capabilities
- [ ] Message encryption
- [ ] Additional chat analysis features
- [ ] Mobile device support
- [ ] Web interface 