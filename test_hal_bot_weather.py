import pytest
from unittest.mock import MagicMock, patch
import json
from hal_bot import HalBot

@pytest.fixture
def bot():
    meshtastic_handler = MagicMock()
    app_config = MagicMock()
    app_config.BOT_NAME = "Eva"
    return HalBot(meshtastic_handler, app_config)

@patch('hal_bot.requests.get')
def test_handle_weather_success(mock_get, bot):
    # Setup mock response
    mock_response = MagicMock()
    mock_response.json.return_value = {
        'current_condition': [{'temp_C': '15', 'weatherDesc': [{'value': 'Sunny'}]}],
        'weather': [
            {}, # today
            {'maxtempC': '20', 'mintempC': '10'} # tomorrow
        ]
    }
    mock_get.return_value = mock_response

    result = bot.handle_command('weather london', '1234', 'sender', 1, False)

    assert result is not None
    assert 'response' in result
    assert '[WEATHER] London' in result['response']
    assert 'Now: 15°C, Sunny' in result['response']
    assert '24h: 10°C-20°C' in result['response']
    assert mock_get.called

@patch('hal_bot.requests.get')
def test_handle_weather_error(mock_get, bot):
    mock_get.side_effect = Exception("API Error")

    result = bot.handle_command('pogoda warszawa', '1234', 'sender', 1, False)

    assert result is not None
    assert 'response' in result
    assert '[WEATHER] Error' in result['response']
