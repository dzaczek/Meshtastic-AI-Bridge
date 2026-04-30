import pytest
from unittest.mock import MagicMock, patch
import json
from ai_bridge import AIBridge

class MockConfig:
    DEFAULT_AI_SERVICE = "openai"
    DEFAULT_PERSONA = "Test Persona"
    OPENAI_API_KEY = "test_key"
    GEMINI_API_KEY = ""
    ENABLE_AI_TRIAGE_ON_CHANNELS = False
    OPENAI_MODEL_NAME = "gpt-3.5-turbo"

@pytest.fixture
def mock_ai_bridge():
    with patch('ai_bridge.OpenAI') as mock_openai:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        bridge = AIBridge(MockConfig())
        return bridge, mock_client

def test_get_response_with_web_search_non_dict_json(mock_ai_bridge):
    bridge, mock_client = mock_ai_bridge

    # Mock the web search analysis to return a JSON list instead of a dict
    mock_analysis_response = MagicMock()
    mock_analysis_response.choices[0].message.content = "[1, 2, 3]"

    # We also need to mock the regular AI response if it falls back to normal response
    mock_normal_response = MagicMock()
    mock_normal_response.choices[0].message.content = "Normal response"

    # Configure the mock to return analysis response first, then normal response
    mock_client.chat.completions.create.side_effect = [
        mock_analysis_response,
        mock_normal_response
    ]

    # Call the method
    response = bridge.get_response_with_web_search([], "Hello", "User", "Node1")

    # Should handle the list JSON gracefully and fall back to normal response
    assert response == "Normal response"

    # Verify that it called create twice
    assert mock_client.chat.completions.create.call_count == 2
