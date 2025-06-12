# Development Guide

This guide provides information for developers who want to contribute to or extend the Meshtastic-AI-Bridge project.

## Development Environment Setup

### Prerequisites

- Python 3.8 or higher
- Git
- A code editor (VS Code, PyCharm, etc.)
- Meshtastic device for testing

### Initial Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/Meshtastic-AI-Bridge.git
cd Meshtastic-AI-Bridge

# Create development environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install development dependencies
pip install -r requirements.txt

# Install additional development tools
pip install pre-commit black flake8 mypy pytest pytest-cov
```

### Development Tools

#### Pre-commit Hooks
```bash
# Install pre-commit hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

#### Code Formatting
```bash
# Format code with Black
black .

# Check code style with flake8
flake8 .

# Type checking with mypy
mypy .
```

#### Testing
```bash
# Run tests
pytest

# Run tests with coverage
pytest --cov=. --cov-report=html

# Run specific test file
pytest test_meshtastic_handler.py
```

## Project Structure

```
Meshtastic-AI-Bridge/
├── main_app.py              # Main application entry point
├── tui_app.py               # Textual-based TUI interface
├── meshtastic_handler.py    # Meshtastic device communication
├── ai_bridge.py             # AI service integration
├── web_spider.py            # Web scraping capabilities
├── ai_web_agent.py          # AI-powered web interaction
├── conversation_manager.py  # Chat history management
├── connection_manager.py    # Connection state management
├── config.py                # Configuration (not in git)
├── config_template.py       # Configuration template
├── requirements.txt         # Python dependencies
├── docs/                    # Documentation
│   ├── INSTALLATION.md
│   ├── CONFIGURATION.md
│   ├── USAGE.md
│   ├── TROUBLESHOOTING.md
│   └── DEVELOPMENT.md
├── conversations/           # Conversation history
├── tests/                   # Test files
└── .github/                 # GitHub workflows
```

## Architecture Overview

### Core Components

#### 1. Main Application (`main_app.py`)
- Entry point for the application
- Handles command-line arguments
- Manages application lifecycle
- Provides console interface

#### 2. TUI Interface (`tui_app.py`)
- Textual-based user interface
- Real-time message display
- Interactive controls
- Channel and user management

#### 3. Meshtastic Handler (`meshtastic_handler.py`)
- Manages Meshtastic device connections
- Handles message sending/receiving
- Supports TCP and serial connections
- Provides device status information

#### 4. AI Bridge (`ai_bridge.py`)
- Integrates with AI services (OpenAI, Gemini)
- Manages AI responses and context
- Handles model selection and configuration
- Provides web scraping capabilities

#### 5. Web Spider (`web_spider.py`)
- Advanced web scraping functionality
- Weather information extraction
- Web search capabilities
- Screenshot capture

#### 6. Conversation Manager (`conversation_manager.py`)
- Manages chat history
- Provides conversation analysis
- Handles message storage
- Implements context management

### Data Flow

```
Meshtastic Device → Meshtastic Handler → Main App → AI Bridge → AI Service
                                                      ↓
Web Spider ← AI Web Agent ← Web Services
```

## Development Guidelines

### Code Style

#### Python Style Guide
- Follow PEP 8 guidelines
- Use Black for code formatting
- Maximum line length: 88 characters
- Use type hints where appropriate

#### Naming Conventions
```python
# Classes: PascalCase
class MeshtasticHandler:
    pass

# Functions and variables: snake_case
def handle_message():
    message_text = "Hello"

# Constants: UPPER_SNAKE_CASE
MAX_RETRY_ATTEMPTS = 3
```

#### Documentation
```python
def process_message(text: str, sender_id: str) -> bool:
    """
    Process incoming message and generate AI response.
    
    Args:
        text: The message text to process
        sender_id: ID of the message sender
        
    Returns:
        bool: True if response was generated, False otherwise
        
    Raises:
        ValueError: If text is empty or invalid
    """
    if not text:
        raise ValueError("Message text cannot be empty")
    
    # Implementation here
    return True
```

### Error Handling

#### Exception Handling
```python
try:
    result = risky_operation()
except SpecificException as e:
    logger.error(f"Specific error occurred: {e}")
    # Handle specific error
except Exception as e:
    logger.error(f"Unexpected error: {e}")
    # Handle general error
finally:
    # Cleanup code
    cleanup_resources()
```

#### Logging
```python
import logging

logger = logging.getLogger(__name__)

def some_function():
    logger.debug("Starting operation")
    try:
        # Operation code
        logger.info("Operation completed successfully")
    except Exception as e:
        logger.error(f"Operation failed: {e}")
        raise
```

### Testing

#### Unit Tests
```python
# test_meshtastic_handler.py
import pytest
from unittest.mock import Mock, patch
from meshtastic_handler import MeshtasticHandler

class TestMeshtasticHandler:
    def setup_method(self):
        self.handler = MeshtasticHandler("tcp", "192.168.1.100")
    
    def test_connection_initialization(self):
        assert self.handler.connection_type == "tcp"
        assert self.handler.device_specifier == "192.168.1.100"
    
    @patch('meshtastic.tcp_interface.TCPInterface')
    def test_tcp_connection(self, mock_tcp):
        mock_interface = Mock()
        mock_tcp.return_value = mock_interface
        
        self.handler.connect()
        
        mock_tcp.assert_called_once_with("192.168.1.100")
        assert self.handler.is_connected
```

#### Integration Tests
```python
# test_integration.py
import pytest
from main_app import MeshtasticAIAppConsole

class TestIntegration:
    def test_full_message_flow(self):
        # Test complete message flow from reception to AI response
        pass
    
    def test_connection_recovery(self):
        # Test connection loss and recovery
        pass
```

#### Mock Testing
```python
# Mock external services
@patch('openai.OpenAI')
def test_ai_response_generation(self, mock_openai):
    mock_client = Mock()
    mock_openai.return_value = mock_client
    mock_client.chat.completions.create.return_value.choices[0].message.content = "Test response"
    
    # Test AI response generation
    response = self.ai_bridge.generate_response("Hello")
    assert response == "Test response"
```

### Configuration Management

#### Environment Variables
```python
import os
from typing import Optional

def get_api_key(service: str) -> Optional[str]:
    """Get API key from environment variable or config."""
    env_key = f"{service.upper()}_API_KEY"
    return os.getenv(env_key) or getattr(config, env_key, None)
```

#### Configuration Validation
```python
def validate_config(config_obj) -> bool:
    """Validate configuration object."""
    required_fields = [
        'MESHTASTIC_CONNECTION_TYPE',
        'MESHTASTIC_DEVICE_SPECIFIER',
        'DEFAULT_AI_SERVICE'
    ]
    
    for field in required_fields:
        if not hasattr(config_obj, field):
            raise ValueError(f"Missing required config field: {field}")
    
    return True
```

## Adding New Features

### 1. Feature Planning

#### Requirements Analysis
- Define the feature requirements
- Identify affected components
- Plan testing strategy
- Consider backward compatibility

#### Design Considerations
- Follow existing patterns
- Maintain separation of concerns
- Consider performance impact
- Plan for error handling

### 2. Implementation

#### Example: Adding New AI Service
```python
# ai_bridge.py
class AIBridge:
    def __init__(self, config):
        self.config = config
        self.services = {
            'openai': self._openai_client,
            'gemini': self._gemini_client,
            'new_service': self._new_service_client  # New service
        }
    
    def _new_service_client(self, message: str) -> str:
        """Implementation for new AI service."""
        # Implementation here
        pass
```

#### Configuration Updates
```python
# config_template.py
# Add new configuration options
NEW_SERVICE_API_KEY = "your-api-key"
NEW_SERVICE_MODEL = "model-name"
```

### 3. Testing

#### Unit Tests
```python
def test_new_service_integration(self):
    """Test new AI service integration."""
    with patch('new_service.Client') as mock_client:
        mock_client.return_value.generate.return_value = "Test response"
        
        response = self.ai_bridge.generate_response("Hello", service="new_service")
        assert response == "Test response"
```

#### Integration Tests
```python
def test_new_service_end_to_end(self):
    """Test complete flow with new service."""
    # Test complete message flow
    pass
```

### 4. Documentation

#### Update Documentation
- Update README.md with new features
- Add configuration examples
- Update usage guide
- Add troubleshooting information

#### Code Documentation
```python
def new_feature_function():
    """
    New feature description.
    
    This function implements the new feature that...
    
    Example:
        >>> result = new_feature_function()
        >>> print(result)
        'Feature result'
    """
    pass
```

## Performance Optimization

### 1. Profiling

#### Using cProfile
```bash
# Profile application
python -m cProfile -o profile.stats main_app.py

# Analyze results
python -c "
import pstats
p = pstats.Stats('profile.stats')
p.sort_stats('cumulative').print_stats(20)
"
```

#### Memory Profiling
```bash
# Install memory profiler
pip install memory-profiler

# Profile memory usage
python -m memory_profiler main_app.py
```

### 2. Optimization Techniques

#### Async/Await
```python
import asyncio

async def async_operation():
    """Use async for I/O operations."""
    result = await some_async_function()
    return result

# Run async function
result = asyncio.run(async_operation())
```

#### Caching
```python
from functools import lru_cache

@lru_cache(maxsize=128)
def expensive_operation(param):
    """Cache expensive operations."""
    # Expensive computation
    return result
```

#### Connection Pooling
```python
import aiohttp

class ConnectionPool:
    def __init__(self):
        self.session = None
    
    async def get_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session
```

## Security Considerations

### 1. API Key Security

#### Environment Variables
```python
# Use environment variables for sensitive data
import os

api_key = os.getenv('OPENAI_API_KEY')
if not api_key:
    raise ValueError("OPENAI_API_KEY environment variable not set")
```

#### Configuration Validation
```python
def validate_api_key(key: str) -> bool:
    """Validate API key format."""
    if not key or key.startswith('sk-') == False:
        return False
    return len(key) > 20
```

### 2. Input Validation

#### Message Validation
```python
def validate_message(text: str) -> bool:
    """Validate incoming message."""
    if not text or len(text) > 1000:
        return False
    
    # Check for malicious content
    if any(pattern in text.lower() for pattern in ['script', 'javascript']):
        return False
    
    return True
```

#### URL Validation
```python
from urllib.parse import urlparse

def validate_url(url: str) -> bool:
    """Validate URL for web scraping."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False
```

## Deployment

### 1. Production Setup

#### Environment Configuration
```bash
# Production environment variables
export OPENAI_API_KEY="sk-production-key"
export GEMINI_API_KEY="production-key"
export DEBUG_MODE="false"
export LOG_LEVEL="INFO"
```

#### Process Management
```bash
# Using systemd
sudo systemctl enable meshtastic-ai-bridge
sudo systemctl start meshtastic-ai-bridge
sudo systemctl status meshtastic-ai-bridge
```

### 2. Monitoring

#### Health Checks
```python
def health_check():
    """Application health check."""
    checks = {
        'meshtastic_connection': check_meshtastic_connection(),
        'ai_service': check_ai_service(),
        'disk_space': check_disk_space(),
        'memory_usage': check_memory_usage()
    }
    return all(checks.values()), checks
```

#### Logging
```python
import logging
from logging.handlers import RotatingFileHandler

def setup_logging():
    """Setup production logging."""
    handler = RotatingFileHandler(
        'app.log', maxBytes=10*1024*1024, backupCount=5
    )
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)
    
    logger = logging.getLogger()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
```

## Contributing

### 1. Development Workflow

#### Branch Strategy
```bash
# Create feature branch
git checkout -b feature/new-feature

# Make changes
git add .
git commit -m "Add new feature"

# Push to remote
git push origin feature/new-feature

# Create pull request
```

#### Commit Messages
```
feat: add new AI service integration
fix: resolve connection timeout issue
docs: update installation guide
test: add unit tests for message handler
refactor: improve error handling in AI bridge
```

### 2. Code Review

#### Review Checklist
- [ ] Code follows style guidelines
- [ ] Tests are included and passing
- [ ] Documentation is updated
- [ ] Error handling is implemented
- [ ] Performance impact is considered
- [ ] Security considerations are addressed

#### Review Process
1. Create pull request
2. Automated tests run
3. Code review by maintainers
4. Address feedback
5. Merge to main branch

### 3. Release Process

#### Version Management
```python
# version.py
__version__ = "5.8.0"
```

#### Release Checklist
- [ ] Update version number to 5.8.0
- [ ] Update changelog with new features
- [ ] Run full test suite
- [ ] Update documentation
- [ ] Create release tag
- [ ] Deploy to production

## Resources

### Documentation
- [Python Documentation](https://docs.python.org/)
- [Textual Documentation](https://textual.textualize.io/)
- [Meshtastic Documentation](https://meshtastic.org/docs/)
- [OpenAI API Documentation](https://platform.openai.com/docs/)

### Tools
- [Black Code Formatter](https://black.readthedocs.io/)
- [Flake8 Linter](https://flake8.pycqa.org/)
- [MyPy Type Checker](https://mypy.readthedocs.io/)
- [Pytest Testing Framework](https://docs.pytest.org/)

### Community
- [GitHub Issues](https://github.com/yourusername/Meshtastic-AI-Bridge/issues)
- [Discord Server](https://discord.gg/meshtastic)
- [Reddit Community](https://reddit.com/r/meshtastic)

## Next Steps

After setting up your development environment:

1. **Explore the Codebase**: Read through the main files
2. **Run Tests**: Ensure everything is working
3. **Make Small Changes**: Start with documentation or minor fixes
4. **Join the Community**: Participate in discussions
5. **Contribute**: Submit pull requests for improvements 