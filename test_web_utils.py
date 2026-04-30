import pytest
import sys
from unittest.mock import patch, MagicMock

# Mock out bs4, requests, etc. for tests if not present
sys.modules['bs4'] = MagicMock()
sys.modules['requests'] = MagicMock()
sys.modules['playwright'] = MagicMock()
sys.modules['playwright.async_api'] = MagicMock()
sys.modules['nest_asyncio'] = MagicMock()

import web_utils

def test_is_safe_url():
    # Valid urls
    assert web_utils.is_safe_url("http://google.com") == True
    assert web_utils.is_safe_url("https://example.com") == True

    # Internal / invalid urls
    assert web_utils.is_safe_url("http://127.0.0.1") == False
    assert web_utils.is_safe_url("http://localhost") == False
    assert web_utils.is_safe_url("http://0.0.0.0") == False
    assert web_utils.is_safe_url("http://169.254.169.254") == False
    assert web_utils.is_safe_url("http://10.0.0.1") == False
    assert web_utils.is_safe_url("http://192.168.1.1") == False
    assert web_utils.is_safe_url("file:///etc/passwd") == False

def test_extract_text_from_url_blocked():
    assert web_utils.extract_text_from_url("http://127.0.0.1") is None
