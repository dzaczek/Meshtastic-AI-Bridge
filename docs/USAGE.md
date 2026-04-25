# Usage Guide

This guide provides detailed instructions for using the Meshtastic-AI-Bridge v5.8 application.

## Getting Started

### 1. Starting the Application

#### Interactive TUI Mode (Default)
```bash
python main_app.py
```
This launches the modern Textual-based user interface.

#### Console Mode
```bash
python main_app.py --no-debug-prints
```
This runs the application in command-line mode.

#### Debug Mode
```bash
python main_app.py -d
```
This enables verbose debug logging for troubleshooting.

### 2. Initial Setup

When you first start the application:

1. **Connection Check**: The app will attempt to connect to your Meshtastic device
2. **AI Service Verification**: It will verify your API keys are working
3. **Interface Loading**: The TUI or console interface will load

## Interactive TUI Mode

### Interface Overview

The TUI interface consists of several key areas:

- **Header**: Application title and status
- **Message Display**: Real-time message feed
- **Input Area**: Text input for commands
- **Sidebar**: Channel and user information
- **Footer**: Keyboard shortcuts and help

### Navigation

#### Keyboard Shortcuts
- `q` or `Ctrl+C`: Quit the application
- `f`: Force AI response
- `Tab`: Navigate between interface elements
- `Enter`: Send message or execute command
- `Esc`: Cancel current operation

#### Mouse Navigation
- Click on messages to select them
- Click on channels in the sidebar to switch
- Use scroll wheel to navigate message history

### Sending Messages

#### As AI
1. Type your message in the input area
2. Press `Enter` to send
3. The AI will process and respond automatically

#### Manual AI Response
1. Press `f` to force an AI response
2. The AI will analyze recent messages and respond

### Channel Management

#### Switching Channels
1. Click on a channel in the sidebar
2. Or use the channel selector in the interface
3. Messages will be filtered by the selected channel

#### Channel Information
The sidebar shows:
- Active channel name
- Number of messages
- Active users
- Channel statistics

### User Statistics

The interface displays:
- User participation percentages
- Message counts per user
- Activity patterns
- Recent activity

## Console Mode

### Available Commands

#### Message Commands
```bash
send <message>          # Send message as AI to active channel
dm <node_id> <message>  # Send direct message to specific node
```

#### AI Control Commands
```bash
persona <text>          # Set AI persona
use_ai <openai|gemini>  # Switch AI service
force_ai                # Force AI response
```

#### Channel Commands
```bash
active_channel <idx>    # Set active channel for AI responses
list_channels           # List available channels
```

#### System Commands
```bash
status                  # Show current status
help                    # Display help
quit                    # Exit application
```

### Example Console Session

```bash
CMD> status
Status: Connected to Meshtastic device
Active Channel: 0
AI Service: OpenAI (GPT-4)
AI Response Probability: 85%

CMD> send Hello everyone!
[AI] Hello! How can I help you today?

CMD> list_channels
Available channels:
0: Primary (Default)
1: Secondary
2: Emergency

CMD> active_channel 1
Switched to channel 1

CMD> use_ai gemini
Switched to Gemini AI service

CMD> quit
Exiting application...
```

## AI Features

### Automatic Responses

The AI automatically responds to messages based on:

1. **Response Probability**: Configured in `config.py`
2. **Message Content**: Questions, requests, or engagement attempts
3. **Context**: Recent conversation history
4. **Triage System**: Smart filtering of when to respond

### AI Persona

The AI's personality is defined by the `DEFAULT_PERSONA` setting:

```python
DEFAULT_PERSONA = (
    "You are a helpful and friendly assistant on a Meshtastic mesh network. "
    "Keep responses concise and relevant to the conversation. "
    "Use natural, conversational language. "
    "Never mention that you are an AI or following a prompt. "
    "Limit responses to 195 characters due to network constraints."
)
```

### AI Services

#### OpenAI (GPT Models)
- **Models**: GPT-4, GPT-4-Turbo, GPT-3.5-Turbo
- **Features**: Advanced reasoning, code generation, creative writing
- **Best for**: Complex questions, technical discussions

#### Google Gemini
- **Models**: Gemini Pro, Gemini 1.5 Pro, Gemini 1.5 Flash
- **Features**: Fast responses, good for general conversation
- **Best for**: Quick responses, casual conversation

### Switching AI Services

#### In TUI Mode
1. Use the AI service selector in the interface
2. Or use the console command: `use_ai <service>`

#### In Console Mode
```bash
use_ai openai    # Switch to OpenAI
use_ai gemini    # Switch to Gemini
```

## Web Integration Features

### Weather Information

The AI can provide weather information:

```
User: "What's the weather like in New York?"
AI: "Currently 72°F and sunny in New York. Light breeze at 8 mph."
```

### Web Search

The AI can search the web for information:

```
User: "Search for latest news about AI"
AI: "Recent AI news: OpenAI released GPT-4o, Google announced Gemini updates..."
```

### URL Analysis

The AI can analyze URLs and extract information:

```
User: "What's on this website: https://example.com"
AI: "This website contains information about..."
```

### Screenshot Capture

For visual analysis, the AI can capture screenshots:

```
User: "Take a screenshot of https://example.com"
AI: "I've captured a screenshot of the website. The page shows..."
```

## Advanced Features

### Message Triage

The triage system determines when the AI should respond:

- **Questions**: Always triggers response
- **Requests**: Triggers response
- **Casual chat**: May not trigger response
- **Acknowledgment**: Usually doesn't trigger response

### Conversation Context

The AI maintains context from recent messages:

- **Context Window**: Configurable number of recent messages
- **Summarization**: Long conversations are summarized
- **Memory**: Important information is retained

### Direct Messaging

Send private messages to specific nodes:

```bash
# Console mode
dm a1b2c3d4 Hello, this is a private message

# TUI mode
# Use the direct message interface
```

### Channel-Specific Behavior

Configure different AI behavior per channel:

```python
# In config.py
CHANNEL_SPECIFIC_SETTINGS = {
    0: {"ai_response_probability": 0.9},  # High AI activity
    1: {"ai_response_probability": 0.3},  # Low AI activity
    2: {"ai_response_probability": 0.0}   # No AI responses
}
```

## Monitoring and Logs

### Log Files

The application creates several log files:

- `interactive.backend.log`: Main application log
- `tui.backend.log`: TUI-specific log
- `conversations/`: Conversation history files

### Log Levels

- **DEBUG**: Detailed debugging information
- **INFO**: General information
- **WARNING**: Warning messages
- **ERROR**: Error messages

### Monitoring Commands

#### In Console Mode
```bash
status          # Current status
show_logs       # Display recent logs
clear_logs      # Clear log buffer
```

#### Log Analysis
```bash
# View recent logs
tail -f interactive.backend.log

# Search for errors
grep "ERROR" interactive.backend.log

# Search for AI responses
grep "AI Response" interactive.backend.log
```

## Performance Optimization

### Memory Management

- **Context Window**: Limit `MAX_HISTORY_MESSAGES_FOR_CONTEXT`
- **Log Rotation**: Regularly clean old log files
- **Conversation Cleanup**: Archive old conversations

### Network Optimization

- **Response Delays**: Adjust AI response timing
- **Connection Monitoring**: Automatic reconnection
- **Timeout Settings**: Optimize for your network

### AI Service Optimization

- **Model Selection**: Choose appropriate model for your needs
- **Response Length**: Keep responses concise
- **Context Management**: Efficient context handling

## Troubleshooting Usage

### Common Issues

#### AI Not Responding
1. Check AI response probability setting
2. Verify API keys are valid
3. Check internet connectivity
4. Review triage system settings

#### Messages Not Appearing
1. Check Meshtastic connection
2. Verify channel selection
3. Check message filters
4. Review log files for errors

#### Interface Issues
1. Restart the application
2. Check terminal compatibility
3. Update Textual library
4. Review system requirements

### Getting Help

1. **Check Logs**: Review log files for error messages
2. **Configuration**: Verify settings in `config.py`
3. **Documentation**: Review this guide and other docs
4. **Community**: Ask for help in the community forums

## Best Practices

### For Users
1. **Start Simple**: Begin with basic configuration
2. **Test Gradually**: Add features one at a time
3. **Monitor Logs**: Regularly check for issues
4. **Backup Config**: Keep backup of working configuration

### For Administrators
1. **Security**: Secure API keys and configuration
2. **Monitoring**: Set up log monitoring
3. **Updates**: Keep dependencies updated
4. **Documentation**: Maintain usage documentation

### For Developers
1. **Testing**: Test changes thoroughly
2. **Logging**: Add appropriate log messages
3. **Error Handling**: Implement proper error handling
4. **Documentation**: Update documentation with changes

## Next Steps

After mastering basic usage:

1. **Advanced Configuration**: Customize AI behavior
2. **Integration**: Connect with other systems
3. **Development**: Contribute to the project
4. **Community**: Share experiences and help others

## Support Resources

- **Documentation**: This guide and other docs
- **Logs**: Application log files
- **Configuration**: `config.py` and templates
- **Community**: User forums and discussions
- **Issues**: GitHub issue tracker 