# Troubleshooting Guide

This guide helps you diagnose and resolve common issues with the Meshtastic-AI-Bridge application.

## Quick Diagnosis

### 1. Check Application Status

```bash
# Start the application and check for errors
python main_app.py

# Check log files for errors
tail -20 interactive.backend.log
```

### 2. Verify Configuration

```bash
# Test configuration import
python -c "import config; print('Config loaded successfully')"

# Check if config.py exists
ls -la config.py
```

### 3. Test Dependencies

```bash
# Test key dependencies
python -c "import meshtastic, textual, openai; print('Dependencies OK')"
```

## Common Issues and Solutions

### Connection Issues

#### Problem: "Meshtastic connection failed"

**Symptoms:**
- Application fails to start
- Error messages about connection timeout
- "Handler reported connected but node_id is None"

**Solutions:**

1. **Check Device Connection**
   ```bash
   # For TCP connections
   ping 192.168.1.100  # Replace with your device IP
   
   # For serial connections
   ls /dev/ttyUSB*  # Linux
   ls /dev/tty.usbserial-*  # macOS
   ```

2. **Verify Configuration**
   ```python
   # In config.py - check these settings
   MESHTASTIC_CONNECTION_TYPE = "tcp"  # or "serial"
   MESHTASTIC_DEVICE_SPECIFIER = "192.168.1.100"  # Your device IP
   MESHTASTIC_TCP_PORT = 4403
   ```

3. **Check Device Permissions (Linux)**
   ```bash
   # Add user to necessary groups
   sudo usermod -a -G dialout $USER
   sudo usermod -a -G tty $USER
   
   # Or temporarily fix permissions
   sudo chmod 666 /dev/ttyUSB0
   ```

4. **Test with Meshtastic CLI**
   ```bash
   # Install meshtastic CLI if not already installed
   pip install meshtastic
   
   # Test connection
   meshtastic --host 192.168.1.100 --port 4403
   ```

#### Problem: "Connection lost" during operation

**Symptoms:**
- Application starts but loses connection
- Messages stop appearing
- Reconnection attempts fail

**Solutions:**

1. **Check Network Stability**
   ```bash
   # Monitor network connection
   ping -c 10 192.168.1.100
   ```

2. **Verify Device Status**
   - Check if device is still powered on
   - Verify network connectivity
   - Check device logs if available

3. **Restart Application**
   ```bash
   # Stop and restart
   Ctrl+C
   python main_app.py
   ```

### AI Service Issues

#### Problem: "OpenAI API key not configured"

**Symptoms:**
- AI responses fail
- Error messages about missing API key
- OpenAI functionality disabled

**Solutions:**

1. **Check API Key Configuration**
   ```python
   # In config.py
   OPENAI_API_KEY = "sk-your-actual-api-key-here"  # Not placeholder
   ```

2. **Verify API Key Validity**
   ```python
   # Test API key
   import openai
   client = openai.OpenAI(api_key="your-key")
   response = client.chat.completions.create(
       model="gpt-3.5-turbo",
       messages=[{"role": "user", "content": "Hello"}]
   )
   ```

3. **Check API Key Format**
   - OpenAI keys start with `sk-`
   - Ensure no extra spaces or characters
   - Check for typos

#### Problem: "Gemini API key not configured"

**Symptoms:**
- Gemini AI service unavailable
- Error messages about missing Gemini key

**Solutions:**

1. **Configure Gemini API Key**
   ```python
   # In config.py
   GEMINI_API_KEY = "your-actual-gemini-api-key-here"
   ```

2. **Test Gemini Connection**
   ```python
   import google.generativeai as genai
   genai.configure(api_key="your-key")
   model = genai.GenerativeModel('gemini-pro')
   response = model.generate_content("Hello")
   ```

#### Problem: "AI not responding to messages"

**Symptoms:**
- AI service is configured but no responses
- Messages are received but AI doesn't reply

**Solutions:**

1. **Check AI Response Settings**
   ```python
   # In config.py
   AI_RESPONSE_PROBABILITY = 0.85  # Should be > 0
   ENABLE_AI_TRIAGE_ON_CHANNELS = True  # If using triage
   ```

2. **Verify Active Channel**
   ```python
   # In config.py
   ACTIVE_MESHTASTIC_CHANNEL_INDEX = 0  # Check channel number
   ```

3. **Test AI Service Manually**
   ```bash
   # In console mode
   force_ai
   ```

4. **Check Triage System**
   ```python
   # In config.py
   TRIAGE_CONTEXT_MESSAGE_COUNT = 3
   TRIAGE_AI_SERVICE = 'openai'  # or 'gemini'
   ```

### Web Scraping Issues

#### Problem: "Playwright not installed"

**Symptoms:**
- Web scraping features disabled
- Error messages about missing Playwright

**Solutions:**

1. **Install Playwright**
   ```bash
   pip install playwright
   playwright install chromium
   ```

2. **Install System Dependencies**
   ```bash
   # Linux
   playwright install-deps
   
   # macOS
   brew install --cask chromium
   ```

3. **Verify Installation**
   ```bash
   python -c "from playwright.async_api import async_playwright; print('Playwright OK')"
   ```

#### Problem: "Web scraping timeout"

**Symptoms:**
- Web scraping operations fail
- Timeout errors in logs

**Solutions:**

1. **Increase Timeout**
   ```python
   # In config.py
   WEB_SCRAPING_TIMEOUT = 60  # Increase from default 30
   ```

2. **Check Network Connectivity**
   ```bash
   # Test internet connection
   curl -I https://www.google.com
   ```

3. **Disable Web Scraping Temporarily**
   ```python
   # In config.py
   DISABLE_WEB_SCRAPING = True
   ```

### Interface Issues

#### Problem: "TUI interface not working"

**Symptoms:**
- Textual interface fails to start
- Display issues or crashes

**Solutions:**

1. **Check Terminal Compatibility**
   ```bash
   # Check terminal type
   echo $TERM
   
   # Try different terminal
   # Use xterm, gnome-terminal, or iTerm2
   ```

2. **Update Textual Library**
   ```bash
   pip install --upgrade textual
   ```

3. **Use Console Mode**
   ```bash
   python main_app.py --no-debug-prints
   ```

#### Problem: "Console mode issues"

**Symptoms:**
- Console commands not working
- Input/output errors

**Solutions:**

1. **Check Python Version**
   ```bash
   python --version  # Should be 3.8+
   ```

2. **Verify UTF-8 Support**
   ```bash
   # Set environment variables
   export PYTHONIOENCODING=utf-8
   export LANG=en_US.UTF-8
   ```

3. **Test Basic Input**
   ```bash
   python -c "input('Test input: ')"
   ```

### Performance Issues

#### Problem: "Application is slow"

**Symptoms:**
- Slow response times
- High memory usage
- Lag in interface

**Solutions:**

1. **Optimize Configuration**
   ```python
   # In config.py
   MAX_HISTORY_MESSAGES_FOR_CONTEXT = 5  # Reduce from 10
   AI_MIN_RESPONSE_DELAY_S = 1  # Reduce delay
   ```

2. **Check System Resources**
   ```bash
   # Monitor memory usage
   top -p $(pgrep python)
   
   # Check disk space
   df -h
   ```

3. **Clean Log Files**
   ```bash
   # Remove old logs
   rm -f *.log
   
   # Archive conversations
   mkdir -p archive
   mv conversations/* archive/
   ```

#### Problem: "High API usage"

**Symptoms:**
- Rapid API calls
- High costs
- Rate limiting

**Solutions:**

1. **Adjust Response Probability**
   ```python
   # In config.py
   AI_RESPONSE_PROBABILITY = 0.3  # Reduce from 0.85
   ```

2. **Increase Cooldown**
   ```python
   # In config.py
   AI_RESPONSE_COOLDOWN_S = 120  # Increase from 60
   ```

3. **Use Efficient Models**
   ```python
   # In config.py
   OPENAI_MODEL_NAME = "gpt-3.5-turbo"  # Instead of gpt-4
   GEMINI_MODEL_NAME = "gemini-1.5-flash-latest"  # Faster model
   ```

## Debugging Techniques

### 1. Enable Debug Logging

```bash
# Start with debug mode
python main_app.py -d

# Check debug output
tail -f interactive.backend.log
```

### 2. Test Individual Components

```bash
# Test Meshtastic connection
python -c "
import meshtastic
interface = meshtastic.tcp_interface.TCPInterface('192.168.1.100')
print('Connection successful')
interface.close()
"

# Test AI service
python -c "
import openai
client = openai.OpenAI(api_key='your-key')
response = client.chat.completions.create(
    model='gpt-3.5-turbo',
    messages=[{'role': 'user', 'content': 'Hello'}]
)
print('AI service working')
"
```

### 3. Check Configuration

```bash
# Validate configuration
python -c "
import config
print(f'OpenAI key: {len(config.OPENAI_API_KEY)} chars')
print(f'Connection type: {config.MESHTASTIC_CONNECTION_TYPE}')
print(f'Device specifier: {config.MESHTASTIC_DEVICE_SPECIFIER}')
"
```

### 4. Monitor System Resources

```bash
# Monitor CPU and memory
htop

# Monitor network
iftop

# Monitor disk I/O
iotop
```

## Log Analysis

### Understanding Log Messages

#### Connection Logs
```
INFO: Meshtastic handler initialized
DEBUG: Attempting TCP connection to 192.168.1.100:4403
ERROR: Connection failed: timeout
```

#### AI Service Logs
```
INFO: OpenAI client initialized
DEBUG: AI response generated: "Hello there!"
ERROR: API call failed: rate limit exceeded
```

#### Web Scraping Logs
```
INFO: Web spider started
DEBUG: Capturing screenshot from https://example.com
ERROR: Screenshot failed: timeout
```

### Common Log Patterns

#### Connection Issues
```bash
# Search for connection errors
grep -i "connection\|timeout\|failed" interactive.backend.log

# Search for specific error types
grep -i "tcp\|serial\|meshtastic" interactive.backend.log
```

#### AI Service Issues
```bash
# Search for AI-related errors
grep -i "openai\|gemini\|api" interactive.backend.log

# Search for response issues
grep -i "response\|ai" interactive.backend.log
```

#### Performance Issues
```bash
# Search for slow operations
grep -i "timeout\|slow\|delay" interactive.backend.log

# Search for memory issues
grep -i "memory\|oom\|kill" interactive.backend.log
```

## Getting Help

### 1. Collect Information

Before asking for help, gather:

- **Error Messages**: Complete error text
- **Log Files**: Relevant log entries
- **Configuration**: Your `config.py` (without API keys)
- **System Info**: OS, Python version, dependencies
- **Steps**: What you were doing when the error occurred

### 2. Search Existing Issues

- Check GitHub issues for similar problems
- Search community forums
- Review documentation

### 3. Create Minimal Reproduction

```bash
# Create minimal test case
python -c "
# Minimal test code here
"
```

### 4. Contact Support

When contacting support:

1. **Be Specific**: Describe the exact problem
2. **Include Context**: What you were trying to do
3. **Provide Logs**: Relevant error messages
4. **Show Configuration**: Your settings (without secrets)
5. **List Steps**: How to reproduce the issue

## Prevention

### 1. Regular Maintenance

```bash
# Update dependencies
pip install --upgrade -r requirements.txt

# Clean old logs
find . -name "*.log" -mtime +7 -delete

# Archive old conversations
tar -czf conversations-$(date +%Y%m%d).tar.gz conversations/
```

### 2. Monitoring

```bash
# Set up log monitoring
tail -f interactive.backend.log | grep -i "error\|warning"

# Monitor API usage
grep -c "API call" interactive.backend.log
```

### 3. Backup Configuration

```bash
# Backup working configuration
cp config.py config.py.backup

# Version control (without secrets)
git add config_template.py
git commit -m "Update configuration template"
```

## Emergency Procedures

### 1. Complete Reset

```bash
# Stop application
Ctrl+C

# Remove all generated files
rm -f *.log
rm -rf conversations/
rm -f config.py

# Reinstall dependencies
pip install --force-reinstall -r requirements.txt

# Recreate configuration
cp config_template.py config.py
# Edit config.py with your settings
```

### 2. Fallback Mode

```bash
# Run with minimal configuration
python main_app.py --no-debug-prints

# Disable AI features temporarily
# Edit config.py: AI_RESPONSE_PROBABILITY = 0.0
```

### 3. Recovery

```bash
# Restore from backup
cp config.py.backup config.py

# Restart application
python main_app.py
```

## Next Steps

After resolving issues:

1. **Document the Solution**: Note what worked for future reference
2. **Update Configuration**: Apply any necessary changes
3. **Test Thoroughly**: Verify everything works as expected
4. **Monitor**: Watch for similar issues in the future
5. **Share**: Help others by sharing your solution 