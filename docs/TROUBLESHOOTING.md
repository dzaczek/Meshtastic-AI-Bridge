# Troubleshooting Guide 🔧

Hey there! Having some issues with your AI Bridge v5.8? Don't worry - we've got your back! This guide will help you diagnose and fix the most common problems. Let's get you back up and running! 🚀

## Quick Diagnosis 🕵️

### 1. Check What's Happening
```bash
# Start the app and see what errors pop up
python main_app.py

# Check the logs for clues
tail -20 interactive.backend.log
```

### 2. Is Your Config Working?
```bash
# Test if your config loads properly
python -c "import config; print('Config loaded successfully')"

# Make sure config.py exists
ls -la config.py
```

### 3. Are Dependencies Happy?
```bash
# Test if all the important packages are working
python -c "import meshtastic, textual, openai; print('Dependencies OK')"
```

## Common Issues & Quick Fixes 🚨

### Connection Woes 🔌

#### Problem: "Meshtastic connection failed"

**What you'll see:**
- App fails to start
- Timeout error messages
- "Handler reported connected but node_id is None"

**Let's fix it:**

1. **Check Your Device Connection**
   ```bash
   # For TCP connections - can you reach your device?
   ping 192.168.1.100  # Replace with your device IP
   
   # For serial connections - is the device there?
   ls /dev/ttyUSB*  # Linux
   ls /dev/tty.usbserial-*  # macOS
   ```

2. **Double-Check Your Settings**
   ```python
   # In config.py - make sure these are right
   MESHTASTIC_CONNECTION_TYPE = "tcp"  # or "serial"
   MESHTASTIC_DEVICE_SPECIFIER = "192.168.1.100"  # Your actual device IP
   MESHTASTIC_TCP_PORT = 4403
   ```

3. **Fix Permissions (Linux Users)**
   ```bash
   # Add yourself to the right groups
   sudo usermod -a -G dialout $USER
   sudo usermod -a -G tty $USER
   
   # Log out and back in for changes to take effect
   ```

4. **Test with Meshtastic CLI**
   ```bash
   # Install meshtastic CLI if you haven't
   pip install meshtastic
   
   # Test the connection directly
   meshtastic --host 192.168.1.100 --port 4403
   ```

#### Problem: "Connection lost" during operation

**What you'll see:**
- App starts but then loses connection
- Messages stop appearing
- Reconnection attempts fail

**Quick fixes:**

1. **Check Your Network**
   ```bash
   # Monitor your network connection
   ping -c 10 192.168.1.100
   ```

2. **Is Your Device Still There?**
   - Check if device is still powered on
   - Verify network connectivity
   - Check device logs if available

3. **Restart the App**
   ```bash
   # Stop and restart
   Ctrl+C
   python main_app.py
   ```

### AI Service Issues 🤖

#### Problem: "OpenAI API key not configured"

**What you'll see:**
- AI responses fail
- Error messages about missing API key
- OpenAI functionality disabled

**Let's fix it:**

1. **Check Your API Key**
   ```python
   # In config.py - make sure it's not a placeholder
   OPENAI_API_KEY = "sk-your-actual-api-key-here"  # Not placeholder text
   ```

2. **Test Your API Key**
   ```python
   # Test if your key actually works
   import openai
   client = openai.OpenAI(api_key="your-key")
   response = client.chat.completions.create(
       model="gpt-3.5-turbo",
       messages=[{"role": "user", "content": "Hello"}]
   )
   ```

3. **Check Your Key Format**
   - OpenAI keys start with `sk-`
   - Make sure there are no extra spaces
   - Check for typos

#### Problem: "Gemini API key not configured"

**What you'll see:**
- Gemini AI service unavailable
- Error messages about missing Gemini key

**Quick fix:**

1. **Add Your Gemini Key**
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

**What you'll see:**
- AI service is configured but no responses
- Messages are received but AI doesn't reply

**Let's troubleshoot:**

1. **Check AI Response Settings**
   ```python
   # In config.py - make sure AI is enabled
   AI_RESPONSE_PROBABILITY = 0.85  # Should be > 0
   ENABLE_AI_TRIAGE_ON_CHANNELS = True  # If using triage
   ```

2. **Verify Active Channel**
   ```python
   # In config.py - check channel number
   ACTIVE_MESHTASTIC_CHANNEL_INDEX = 0  # Make sure this is right
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

### Web Scraping Issues 🌐

#### Problem: "Playwright not installed"

**What you'll see:**
- Web scraping features disabled
- Error messages about missing Playwright

**Quick fix:**

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

**What you'll see:**
- Web scraping operations fail
- Timeout errors in logs

**Solutions:**

1. **Increase Timeout**
   ```python
   # In config.py
   WEB_SCRAPING_TIMEOUT = 60  # Increase from default 30
   ```

2. **Check Your Internet**
   ```bash
   # Test internet connection
   curl -I https://www.google.com
   ```

3. **Disable Web Scraping Temporarily**
   ```python
   # In config.py
   DISABLE_WEB_SCRAPING = True
   ```

### Interface Issues 🖥️

#### Problem: "TUI interface not working"

**What you'll see:**
- Textual interface fails to start
- Display issues or crashes

**Let's fix it:**

1. **Check Your Terminal**
   ```bash
   # Check terminal type
   echo $TERM
   
   # Try a different terminal
   # Use xterm, gnome-terminal, or iTerm2
   ```

2. **Update Textual Library**
   ```bash
   pip install --upgrade textual
   ```

3. **Use Console Mode Instead**
   ```bash
   python main_app.py --no-debug-prints
   ```

#### Problem: "Console mode issues"

**What you'll see:**
- Console commands not working
- Input/output errors

**Quick fixes:**

1. **Check Python Version**
   ```bash
   python --version  # Should be 3.8+
   ```

2. **Fix UTF-8 Support**
   ```bash
   # Set environment variables
   export PYTHONIOENCODING=utf-8
   export LANG=en_US.UTF-8
   ```

3. **Test Basic Input**
   ```bash
   python -c "input('Test input: ')"
   ```

### Performance Issues 🐌

#### Problem: "Application is slow"

**What you'll see:**
- Slow response times
- High memory usage
- Lag in interface

**Optimization tips:**

1. **Tweak Configuration**
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

3. **Clean Up Logs**
   ```bash
   # Remove old logs
   rm -f *.log
   
   # Archive conversations
   mkdir -p archive
   mv conversations/* archive/
   ```

#### Problem: "High API usage"

**What you'll see:**
- Rapid API calls
- High costs
- Rate limiting

**Cost-saving tips:**

1. **Reduce AI Activity**
   ```python
   # In config.py
   AI_RESPONSE_PROBABILITY = 0.3  # Reduce from 0.85
   ```

2. **Increase Cooldown**
   ```python
   # In config.py
   AI_RESPONSE_COOLDOWN_S = 120  # Increase from 60
   ```

3. **Use Cheaper Models**
   ```python
   # In config.py
   OPENAI_MODEL_NAME = "gpt-3.5-turbo"  # Instead of gpt-4
   GEMINI_MODEL_NAME = "gemini-1.5-flash-latest"  # Faster model
   ```

## Debugging Like a Pro 🕵️

### 1. Enable Debug Logging
```bash
# Start with debug mode to see what's happening
python main_app.py -d

# Watch the debug output
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

### 3. Check Your Configuration
```bash
# Validate your configuration
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

## Understanding Your Logs 📋

### What to Look For

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

### Finding the Problem

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

## Getting Help When You're Stuck 🆘

### 1. Gather Information
Before asking for help, collect:

- **Error Messages**: The complete error text
- **Log Files**: Relevant log entries
- **Configuration**: Your `config.py` (without API keys!)
- **System Info**: OS, Python version, dependencies
- **Steps**: What you were doing when it broke

### 2. Search for Solutions
- Check GitHub issues for similar problems
- Search community forums
- Review our documentation

### 3. Create a Minimal Test
```bash
# Create a minimal test case
python -c "
# Minimal test code here
"
```

### 4. Reach Out for Help
When contacting support:

1. **Be Specific**: Describe exactly what's wrong
2. **Include Context**: What were you trying to do?
3. **Provide Logs**: Share relevant error messages
4. **Show Config**: Your settings (without secrets!)
5. **List Steps**: How to reproduce the issue

## Prevention is Better Than Cure 🛡️

### 1. Regular Maintenance
```bash
# Update dependencies
pip install --upgrade -r requirements.txt

# Clean old logs
find . -name "*.log" -mtime +7 -delete

# Archive old conversations
tar -czf conversations-$(date +%Y%m%d).tar.gz conversations/
```

### 2. Monitor Your System
```bash
# Set up log monitoring
tail -f interactive.backend.log | grep -i "error\|warning"

# Monitor API usage
grep -c "API call" interactive.backend.log
```

### 3. Backup Your Configuration
```bash
# Backup working configuration
cp config.py config.py.backup

# Version control (without secrets)
git add config_template.py
git commit -m "Update configuration template"
```

## Emergency Procedures 🚨

### 1. Complete Reset (Nuclear Option)
```bash
# Stop the application
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

## What to Do After Fixing Issues ✅

After resolving problems:

1. **Document the Solution**: Note what worked for future reference
2. **Update Configuration**: Apply any necessary changes
3. **Test Thoroughly**: Make sure everything works as expected
4. **Monitor**: Watch for similar issues in the future
5. **Share**: Help others by sharing your solution

## Still Stuck? 🤔

If you've tried everything and it's still not working:

1. **Take a Break**: Sometimes stepping away helps!
2. **Check Our Documentation**: We have comprehensive guides
3. **Join the Community**: Other users might have solved this
4. **Open an Issue**: We're here to help!

---

**Remember: Every problem has a solution! 💪**

Most issues are just configuration problems or missing dependencies. With a little patience and these troubleshooting steps, you'll have your AI Bridge running smoothly in no time!

Happy troubleshooting! 🔧✨ 