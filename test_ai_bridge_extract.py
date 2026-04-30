import sys
import subprocess
from unittest.mock import MagicMock, patch

# Mock dependencies
sys.modules['openai'] = MagicMock()
sys.modules['google'] = MagicMock()
sys.modules['google.generativeai'] = MagicMock()
sys.modules['web_utils'] = MagicMock()
sys.modules['web_agent'] = MagicMock()

import pytest
from ai_bridge import AIBridge

class DummyConfig:
    DEFAULT_AI_SERVICE = 'openai'
    DEFAULT_PERSONA = 'default'
    OPENAI_API_KEY = 'test_key'
    GEMINI_API_KEY = 'test_key'

def test_extract_specific_info_no_spider():
    bridge = AIBridge(DummyConfig())
    bridge.web_spider_available = False
    result = bridge.extract_specific_info('http://example.com', 'temperature')
    assert result == "[Specific data extraction not available - web_spider module missing]"

def test_extract_specific_info_unknown_type():
    bridge = AIBridge(DummyConfig())
    bridge.web_spider_available = True
    result = bridge.extract_specific_info('http://example.com', 'unknown_type')
    assert "Unknown info type: unknown_type" in result

@patch('ai_bridge.extract_specific_data_sync')
def test_extract_specific_info_success(mock_extract):
    bridge = AIBridge(DummyConfig())
    bridge.web_spider_available = True
    mock_extract.return_value = {'temperature': '25C'}
    result = bridge.extract_specific_info('http://example.com', 'temperature')
    assert result == "Found temperature: 25C"
    mock_extract.assert_called_once()

@patch('ai_bridge.extract_specific_data_sync')
def test_extract_specific_info_failure(mock_extract):
    bridge = AIBridge(DummyConfig())
    bridge.web_spider_available = True
    mock_extract.side_effect = Exception("Test Exception")
    result = bridge.extract_specific_info('http://example.com', 'temperature')
    assert result == "[Could not extract temperature from http://example.com]"
    assert mock_extract.call_count == 4

def test_extract_specific_info_outer_exception():
    bridge = AIBridge(DummyConfig())
    bridge.web_spider_available = True

    class Unhashable:
        def __hash__(self):
            raise TypeError("Cannot hash")
        def __eq__(self, other):
            return False

    result = bridge.extract_specific_info('http://example.com', Unhashable())
    assert "[Error extracting" in result

def test_extract_text_from_url_fallback():
    script = """
import sys
sys.modules['web_utils'] = None
import ai_bridge
assert ai_bridge.WEB_UTILS_AVAILABLE is False
assert ai_bridge.extract_text_from_url("http://example.com") is None
print("SUCCESS")
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert "SUCCESS" in result.stdout
    assert result.returncode == 0
