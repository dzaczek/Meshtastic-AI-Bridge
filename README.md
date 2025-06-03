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

The application now runs in interactive TUI mode by default:

```bash
python main_app.py
```

You can also explicitly enable interactive mode:
```bash
python main_app.py -i
```

Additional options:
- `--no-debug-prints`: Disable verbose DEBUG prints
- `-d` or `--debug`: Enable ultra-verbose debug logging

### Chat Analysis Tool

To analyze chat history:
