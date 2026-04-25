# Detailed Installation Guide

This guide provides step-by-step instructions for installing and setting up the Meshtastic-AI-Bridge v5.8 application.

## Prerequisites

### System Requirements
- **Operating System**: Linux, macOS, or Windows
- **Python**: Version 3.8 or higher
- **Memory**: Minimum 2GB RAM (4GB recommended)
- **Storage**: 500MB free space
- **Network**: Internet connection for AI services and package installation

### Hardware Requirements
- **Meshtastic Device**: Any compatible Meshtastic device (T-Beam, Heltec, etc.)
- **Connection**: USB cable (for serial) or network connection (for TCP)

## Step-by-Step Installation

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/Meshtastic-AI-Bridge.git
cd Meshtastic-AI-Bridge
```

### 2. Python Environment Setup

#### Option A: Virtual Environment (Recommended)

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Linux/macOS:
source venv/bin/activate
# On Windows:
venv\Scripts\activate
```

#### Option B: Conda Environment

```bash
# Create conda environment
conda create -n meshtastic-ai python=3.9
conda activate meshtastic-ai
```

### 3. Install Dependencies

```bash
# Install Python packages
pip install -r requirements.txt

# Install Playwright browsers (required for web scraping)
playwright install chromium
```

### 4. Platform-Specific Setup

#### Linux Setup

```bash
# Install system dependencies
sudo apt-get update
sudo apt-get install -y python3-pip python3-venv

# Add user to dialout group for serial access
sudo usermod -a -G dialout $USER
sudo usermod -a -G tty $USER

# Log out and back in for group changes to take effect
```

#### macOS Setup

```bash
# Install Homebrew if not already installed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python (if not already installed)
brew install python@3.9
```

#### Windows Setup

```bash
# Install Python from https://python.org if not already installed
# Ensure "Add Python to PATH" is checked during installation

# Install Visual C++ Build Tools (if needed)
# Download from: https://visualstudio.microsoft.com/visual-cpp-build-tools/
```

### 5. Configuration Setup

```bash
# Copy configuration template
cp config_template.py config.py

# Edit configuration file
nano config.py  # or use your preferred editor
```

### 6. API Keys Setup

#### OpenAI API Key
1. Visit [OpenAI Platform](https://platform.openai.com/api-keys)
2. Sign in or create an account
3. Click "Create new secret key"
4. Copy the key and add it to `config.py`:
   ```python
   OPENAI_API_KEY = "sk-your-actual-api-key-here"
   ```

#### Google Gemini API Key
1. Visit [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Sign in with your Google account
3. Click "Create API Key"
4. Copy the key and add it to `config.py`:
   ```python
   GEMINI_API_KEY = "your-actual-gemini-api-key-here"
   ```

### 7. Meshtastic Device Setup

#### TCP Connection (Recommended)
1. Ensure your Meshtastic device is connected to the network
2. Find the device's IP address (check device settings or router)
3. Configure in `config.py`:
   ```python
   MESHTASTIC_CONNECTION_TYPE = "tcp"
   MESHTASTIC_DEVICE_SPECIFIER = "192.168.1.100"  # Your device IP
   MESHTASTIC_TCP_PORT = 4403
   ```

#### Serial Connection
1. Connect device via USB
2. Find the device path:
   - **Linux**: `/dev/ttyUSB0` or `/dev/ttyACM0`
   - **macOS**: `/dev/tty.usbserial-*`
   - **Windows**: `COM3`, `COM4`, etc.
3. Configure in `config.py`:
   ```python
   MESHTASTIC_CONNECTION_TYPE = "serial"
   MESHTASTIC_DEVICE_SPECIFIER = "/dev/ttyUSB0"  # Your device path
   ```

## Verification

### 1. Test Installation

```bash
# Test Python installation
python --version

# Test package installation
python -c "import meshtastic, textual, openai; print('All packages installed successfully')"
```

### 2. Test Configuration

```bash
# Test configuration import
python -c "import config; print('Configuration loaded successfully')"
```

### 3. Test Meshtastic Connection

```bash
# Run the application
python main_app.py

# Check for connection messages in the output
```

## Troubleshooting Installation

### Common Issues

#### Python Version Issues
```bash
# Check Python version
python --version

# If version is too old, install newer version
# Linux: sudo apt-get install python3.9
# macOS: brew install python@3.9
# Windows: Download from python.org
```

#### Permission Issues (Linux)
```bash
# Fix serial port permissions
sudo chmod 666 /dev/ttyUSB0

# Or add user to groups permanently
sudo usermod -a -G dialout $USER
sudo usermod -a -G tty $USER
```

#### Playwright Installation Issues
```bash
# Reinstall Playwright
pip uninstall playwright
pip install playwright
playwright install chromium

# If still having issues, try with system dependencies
playwright install-deps
```

#### Virtual Environment Issues
```bash
# If virtual environment is not working
python -m venv --clear venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Getting Help

If you encounter issues during installation:

1. Check the [troubleshooting section](../README.md#troubleshooting) in the main README
2. Review the logs in `interactive.backend.log`
3. Open an issue on GitHub with:
   - Your operating system and version
   - Python version
   - Complete error message
   - Steps you followed

## Next Steps

After successful installation:

1. Read the [Configuration Guide](CONFIGURATION.md)
2. Review the [Usage Guide](USAGE.md)
3. Check the [Troubleshooting Guide](TROUBLESHOOTING.md)
4. Join the community discussions 