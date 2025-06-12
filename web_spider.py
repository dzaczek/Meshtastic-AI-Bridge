# web_spider.py
import asyncio
from playwright.async_api import async_playwright
import re
import json
import time
from typing import Dict, List, Optional, Any
from bs4 import BeautifulSoup
import requests
from urllib.parse import urljoin, urlparse
import nest_asyncio

class WebSpider:
    """
    Advanced web spider for extracting specific information from websites
    """
    
    def __init__(self, timeout_s=30):
        self.timeout_s = timeout_s
        self.browser = None
        self.context = None
        self.page = None
        
    async def __aenter__(self):
        """Async context manager entry"""
        await self.start_browser()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close_browser()
        
    async def start_browser(self):
        """Start browser session"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        self.context = await self.browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 WebSpider/1.0",
            viewport={'width': 1280, 'height': 720}
        )
        self.page = await self.context.new_page()
        
    async def close_browser(self):
        """Close browser session"""
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if hasattr(self, 'playwright'):
            await self.playwright.stop()
            
    async def navigate_to_page(self, url: str, wait_for_selector: Optional[str] = None):
        """Navigate to page and wait for content to load"""
        try:
            await self.page.goto(url, timeout=self.timeout_s * 1000, wait_until="domcontentloaded")
            if wait_for_selector:
                await self.page.wait_for_selector(wait_for_selector, timeout=10000)
            await asyncio.sleep(2)  # Allow JS to load
            return True
        except Exception as e:
            print(f"Error navigating to {url}: {e}")
            return False
            
    async def search_for_text(self, search_text: str, selector: Optional[str] = None) -> List[str]:
        """Search for specific text on the page"""
        try:
            if selector:
                elements = await self.page.query_selector_all(selector)
                results = []
                for element in elements:
                    text = await element.text_content()
                    if text and search_text.lower() in text.lower():
                        results.append(text.strip())
                return results
            else:
                # Search in all text content
                content = await self.page.content()
                soup = BeautifulSoup(content, 'html.parser')
                text_content = soup.get_text()
                lines = text_content.split('\n')
                return [line.strip() for line in lines if search_text.lower() in line.lower() and line.strip()]
        except Exception as e:
            print(f"Error searching for text '{search_text}': {e}")
            return []
            
    async def extract_weather_data(self, city: str) -> Dict[str, Any]:
        """Extract weather data for a specific city"""
        weather_data = {
            'city': city,
            'temperature': None,
            'condition': None,
            'humidity': None,
            'wind': None,
            'source': None,
            'timestamp': time.time()
        }
        
        # Try multiple weather sources
        sources = [
            f"https://www.google.com/search?q=weather+{city}",
            f"https://weather.com/weather/today/l/{city}",
            f"https://www.accuweather.com/en/search-locations?query={city}"
        ]
        
        for source_url in sources:
            try:
                if await self.navigate_to_page(source_url):
                    # Look for temperature patterns
                    temp_patterns = [
                        r'(\d+)\s*°[CF]',  # 25°C or 77°F
                        r'(\d+)\s*degrees',  # 25 degrees
                        r'temperature[:\s]*(\d+)',  # temperature: 25
                    ]
                    
                    page_content = await self.page.content()
                    for pattern in temp_patterns:
                        matches = re.findall(pattern, page_content, re.IGNORECASE)
                        if matches:
                            weather_data['temperature'] = matches[0]
                            weather_data['source'] = source_url
                            break
                            
                    # Look for weather condition
                    condition_keywords = ['sunny', 'cloudy', 'rainy', 'snow', 'clear', 'overcast']
                    for keyword in condition_keywords:
                        if keyword in page_content.lower():
                            weather_data['condition'] = keyword
                            break
                            
                    if weather_data['temperature']:
                        break
                        
            except Exception as e:
                print(f"Error extracting weather from {source_url}: {e}")
                continue
                
        return weather_data
        
    async def search_duckduckgo(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        """Search DuckDuckGo and extract results"""
        results = []
        try:
            search_url = f"https://duckduckgo.com/?q={query.replace(' ', '+')}"
            if await self.navigate_to_page(search_url):
                # Extract search results - try different selectors
                selectors_to_try = ["h2", "h3", ".result__title", ".result__a", "a[data-testid='result-title']"]
                
                for selector in selectors_to_try:
                    try:
                        result_elements = await self.page.query_selector_all(selector)
                        if result_elements:
                            for i, element in enumerate(result_elements[:max_results]):
                                try:
                                    title = await element.text_content()
                                    if title and len(title.strip()) > 10:
                                        # Try to get the link
                                        link_element = await element.query_selector("a")
                                        link = await link_element.get_attribute("href") if link_element else None
                                        
                                        results.append({
                                            'title': title.strip(),
                                            'url': link,
                                            'rank': i + 1
                                        })
                                except Exception as e:
                                    continue
                            if results:
                                break
                    except Exception as e:
                        continue
                        
        except Exception as e:
            print(f"Error searching DuckDuckGo: {e}")
            
        # Fallback to Google if DuckDuckGo fails
        if not results:
            try:
                google_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
                if await self.navigate_to_page(google_url):
                    # Try to extract Google results
                    result_elements = await self.page.query_selector_all("h3")
                    for i, element in enumerate(result_elements[:max_results]):
                        try:
                            title = await element.text_content()
                            if title and len(title.strip()) > 10:
                                results.append({
                                    'title': title.strip(),
                                    'url': None,  # Google links are more complex
                                    'rank': i + 1
                                })
                        except Exception as e:
                            continue
            except Exception as e:
                print(f"Error with Google fallback: {e}")
            
        return results
        
    async def extract_specific_data(self, url: str, data_spec: Dict[str, str]) -> Dict[str, Any]:
        """
        Extract specific data from a page based on selectors
        
        data_spec example:
        {
            'temperature': '.temp-value',
            'price': '.price-tag',
            'title': 'h1',
            'description': '.description'
        }
        """
        extracted_data = {}
        
        try:
            if await self.navigate_to_page(url):
                for field_name, selector in data_spec.items():
                    try:
                        element = await self.page.query_selector(selector)
                        if element:
                            value = await element.text_content()
                            extracted_data[field_name] = value.strip() if value else None
                        else:
                            extracted_data[field_name] = None
                    except Exception as e:
                        print(f"Error extracting {field_name}: {e}")
                        extracted_data[field_name] = None
                        
        except Exception as e:
            print(f"Error extracting data from {url}: {e}")
            
        return extracted_data
        
    async def fill_form_and_submit(self, url: str, form_data: Dict[str, str], submit_selector: str = "input[type='submit'], button[type='submit']"):
        """Fill a form and submit it"""
        try:
            if await self.navigate_to_page(url):
                for field_name, value in form_data.items():
                    try:
                        await self.page.fill(f'[name="{field_name}"], #{field_name}, .{field_name}', value)
                    except Exception as e:
                        print(f"Error filling field {field_name}: {e}")
                        
                # Submit form
                submit_button = await self.page.query_selector(submit_selector)
                if submit_button:
                    await submit_button.click()
                    await asyncio.sleep(3)  # Wait for submission
                    return True
                    
        except Exception as e:
            print(f"Error filling form: {e}")
            
        return False
        
    def sync_wrapper(self, coro):
        """Synchronous wrapper for async methods"""
        try:
            loop = asyncio.get_event_loop_policy().get_event_loop()
            if loop.is_running():
                nest_asyncio.apply(loop)
            return loop.run_until_complete(coro)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)

# Convenience functions for synchronous use
def extract_weather_sync(city: str) -> Dict[str, Any]:
    """Synchronous weather extraction"""
    async def _extract_weather():
        async with WebSpider() as spider:
            return await spider.extract_weather_data(city)
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(_extract_weather())
    finally:
        loop.close()

def search_duckduckgo_sync(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """Synchronous DuckDuckGo search"""
    async def _search_duckduckgo():
        async with WebSpider() as spider:
            return await spider.search_duckduckgo(query, max_results)
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(_search_duckduckgo())
    finally:
        loop.close()

def extract_specific_data_sync(url: str, data_spec: Dict[str, str]) -> Dict[str, Any]:
    """Synchronous data extraction"""
    async def _extract_data():
        async with WebSpider() as spider:
            return await spider.extract_specific_data(url, data_spec)
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(_extract_data())
    finally:
        loop.close()

if __name__ == "__main__":
    # Test the spider
    print("Testing WebSpider...")
    
    # Test weather extraction
    print("\n--- Testing Weather Extraction ---")
    weather = extract_weather_sync("Zurich")
    print(f"Weather data: {weather}")
    
    # Test DuckDuckGo search
    print("\n--- Testing DuckDuckGo Search ---")
    results = search_duckduckgo_sync("current temperature Zurich", 3)
    print(f"Search results: {results}") 