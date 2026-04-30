import sys
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
    # Setup
    bridge = AIBridge(DummyConfig())
    bridge.web_spider_available = False

    # Execution
    result = bridge.extract_specific_info('http://example.com', 'temperature')

    # Assertion
    assert result == "[Specific data extraction not available - web_spider module missing]"

def test_extract_specific_info_unknown_type():
    # Setup
    bridge = AIBridge(DummyConfig())
    bridge.web_spider_available = True

    # Execution
    result = bridge.extract_specific_info('http://example.com', 'unknown_type')

    # Assertion
    assert "Unknown info type: unknown_type" in result

@patch('ai_bridge.extract_specific_data_sync')
def test_extract_specific_info_success(mock_extract):
    # Setup
    bridge = AIBridge(DummyConfig())
    bridge.web_spider_available = True

    # Configure mock to return valid data for the first selector
    mock_extract.return_value = {'temperature': '25C'}

    # Execution
    result = bridge.extract_specific_info('http://example.com', 'temperature')

    # Assertion
    assert result == "Found temperature: 25C"
    mock_extract.assert_called_once()

@patch('ai_bridge.extract_specific_data_sync')
def test_extract_specific_info_failure(mock_extract):
    # Setup
    bridge = AIBridge(DummyConfig())
    bridge.web_spider_available = True

    # Configure mock to raise an exception for all selectors
    mock_extract.side_effect = Exception("Test Exception")

    # Execution
    result = bridge.extract_specific_info('http://example.com', 'temperature')

    # Assertion
    assert result == "[Could not extract temperature from http://example.com]"
    assert mock_extract.call_count == 4 # Should try all 4 selectors

def test_extract_specific_info_outer_exception():
    # Setup
    bridge = AIBridge(DummyConfig())
    bridge.web_spider_available = True

    # Passing an unhashable info_type to trigger TypeError in 'info_type not in selectors'
    class Unhashable:
        def __hash__(self):
            raise TypeError("Cannot hash")
        def __eq__(self, other):
            return False

    # Execution
    result = bridge.extract_specific_info('http://example.com', Unhashable())

    # Assertion
    assert "[Error extracting" in result
