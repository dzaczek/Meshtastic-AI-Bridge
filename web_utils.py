# web_utils.py
import asyncio
from playwright.async_api import async_playwright
import time # For synchronous version if preferred, or for delays
from bs4 import BeautifulSoup
import requests
import nest_asyncio # Make sure this is installed: pip install nest_asyncio

# Asynchronous version (recommended for non-blocking IO)
async def capture_screenshot_from_url_async(url_to_capture: str, timeout_ms: int = 15000) -> bytes | None:
    """
    Captures a screenshot of a given URL using Playwright (async).
    Returns screenshot as PNG bytes or None if an error occurs.
    """
    print(f"WEB_UTILS: Attempting async screenshot for URL: {url_to_capture}")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 MeshtasticAIBridge/1.0",
                # Consider viewport size for consistent screenshots
                viewport={'width': 1280, 'height': 720}
            )
            page = await context.new_page()
            await page.goto(url_to_capture, timeout=timeout_ms, wait_until="networkidle")
            await asyncio.sleep(2) # Allow time for JS rendering after networkidle
            screenshot_bytes = await page.screenshot(type="png", full_page=False) # full_page=False for viewport
            await browser.close()
            print(f"WEB_UTILS: Successfully captured screenshot for {url_to_capture}")
            return screenshot_bytes
    except Exception as e:
        print(f"WEB_UTILS: Error capturing async screenshot for {url_to_capture}: {e}")
        return None

def capture_screenshot_from_url_sync(url_to_capture: str, timeout_s: int = 15) -> bytes | None:
    """
    Synchronous wrapper for capture_screenshot_from_url_async.
    """
    print(f"WEB_UTILS: Initiating sync screenshot for {url_to_capture}")
    try:
        loop = asyncio.get_event_loop_policy().get_event_loop()
        if loop.is_running():
            print("WEB_UTILS: Asyncio loop is already running. Applying nest_asyncio.")
            nest_asyncio.apply(loop) # Apply to the currently running loop
            # Re-get loop just in case nest_asyncio modified how it's accessed, though usually not needed.
            # loop = asyncio.get_event_loop_policy().get_event_loop() 
        return loop.run_until_complete(capture_screenshot_from_url_async(url_to_capture, timeout_ms=timeout_s * 1000))
    except RuntimeError as e:
        if "There is no current event loop in thread" in str(e) or "Event loop is closed" in str(e):
            print("WEB_UTILS: No current event loop, creating a new one.")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(capture_screenshot_from_url_async(url_to_capture, timeout_ms=timeout_s * 1000))
        else:
            print(f"WEB_UTILS: RuntimeError managing event loop for sync screenshot: {e}")
            return None
    except Exception as e:
        print(f"WEB_UTILS: General error in sync screenshot wrapper for {url_to_capture}: {e}")
        return None

def extract_text_from_url(url: str, timeout_s: int = 10) -> str | None:
    """
    Extracts visible text content from a URL using requests and BeautifulSoup.
    """
    print(f"WEB_UTILS: Attempting to extract text from URL: {url}")
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 MeshtasticAIBridge/1.0'
        }
        response = requests.get(url, headers=headers, timeout=timeout_s)
        response.raise_for_status() 

        soup = BeautifulSoup(response.content, 'html.parser')
        for script_or_style in soup(["script", "style", "header", "footer", "nav", "aside"]): # Remove more non-content tags
            script_or_style.decompose()
        text = soup.get_text(separator=' ', strip=True)
        
        # Basic text cleaning: replace multiple newlines/spaces
        text = ' '.join(text.split())

        max_text_length = 5000 # Allow more text for AI to summarize
        if len(text) > max_text_length:
            text = text[:max_text_length] + "..."
        print(f"WEB_UTILS: Successfully extracted text from {url} (length: {len(text)})")
        return text
    except requests.exceptions.RequestException as e:
        print(f"WEB_UTILS: Error fetching URL {url} for text extraction: {e}")
        return None
    except Exception as e:
        print(f"WEB_UTILS: Error extracting text from {url}: {e}")
        return None

if __name__ == '__main__':
    # Test functions
    test_url = "https://www.meshtastic.org" 
    # test_url = "https://www.bbc.com/news" # More complex page
    print(f"\nTesting with URL: {test_url}")

    print("\n--- Testing Screenshot (Sync) ---")
    screenshot_data = capture_screenshot_from_url_sync(test_url, timeout_s=25) # Increased timeout for testing
    if screenshot_data:
        with open("test_screenshot.png", "wb") as f:
            f.write(screenshot_data)
        print("Screenshot saved to test_screenshot.png")
    else:
        print("Failed to capture screenshot.")

    print("\n--- Testing Text Extraction ---")
    extracted_text = extract_text_from_url(test_url, timeout_s=15)
    if extracted_text:
        print(f"Extracted Text (first 500 chars):\n{extracted_text[:500]}...")
    else:
        print("Failed to extract text.")
