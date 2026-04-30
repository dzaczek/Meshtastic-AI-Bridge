import pytest
import sys
import subprocess

def test_extract_text_from_url_available():
    import ai_bridge
    import web_utils
    assert ai_bridge.WEB_UTILS_AVAILABLE is True
    assert ai_bridge.extract_text_from_url == web_utils.extract_text_from_url

def test_extract_text_from_url_fallback():
    # Run in a separate process with a modified sys.path or patched import
    # to avoid polluting the pytest process and causing protobuf errors.
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
