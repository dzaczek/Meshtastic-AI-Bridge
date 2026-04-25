# web_agent.py
"""
Unified web agent - merges web_spider.py and ai_web_agent.py into one module.

Provides:
- Weather extraction
- DuckDuckGo / Google search
- Specific data extraction from URLs
- AI-powered query analysis and intelligent scraping
"""

import asyncio
import re
import json
import time
from typing import Dict, List, Optional, Any
from bs4 import BeautifulSoup
import requests
from urllib.parse import unquote

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

try:
    import nest_asyncio
    NEST_ASYNCIO_AVAILABLE = True
except ImportError:
    NEST_ASYNCIO_AVAILABLE = False


class WebAgent:
    """
    All-in-one web agent.  Use as async context manager:

        async with WebAgent() as agent:
            results = await agent.search("meshtastic firmware")
    """

    def __init__(self, openai_client=None, timeout_s: int = 30):
        self.openai_client = openai_client
        self.timeout_s = timeout_s
        self.browser = None
        self.context = None
        self.page = None

    # --- Context manager ---------------------------------------------------

    async def __aenter__(self):
        await self._start_browser()
        return self

    async def __aexit__(self, *exc):
        await self._close_browser()

    async def _start_browser(self):
        if not PLAYWRIGHT_AVAILABLE:
            return
        self._pw = await async_playwright().start()
        self.browser = await self._pw.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        self.context = await self.browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/91.0.4472.124 Safari/537.36 "
                "MeshtasticAIBridge/2.0"
            ),
            viewport={'width': 1280, 'height': 720},
        )
        self.page = await self.context.new_page()

    async def _close_browser(self):
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if hasattr(self, '_pw'):
            await self._pw.stop()

    async def _goto(self, url: str, wait_sel: Optional[str] = None) -> bool:
        if not self.page:
            return False
        try:
            await self.page.goto(url, timeout=self.timeout_s * 1000,
                                 wait_until="domcontentloaded")
            if wait_sel:
                await self.page.wait_for_selector(wait_sel, timeout=10000)
            await asyncio.sleep(2)
            return True
        except Exception as e:
            print(f"WebAgent: Error navigating to {url}: {e}")
            return False

    # --- Weather -----------------------------------------------------------

    async def extract_weather(self, city: str) -> Dict[str, Any]:
        data = {'city': city, 'temperature': None, 'condition': None,
                'source': None, 'timestamp': time.time()}

        sources = [
            f"https://www.google.com/search?q=weather+{city}",
            f"https://weather.com/weather/today/l/{city}",
        ]
        temp_patterns = [
            r'(\d+)\s*°[CF]', r'(\d+)\s*degrees',
            r'temperature[:\s]*(\d+)',
        ]
        condition_kw = ['sunny', 'cloudy', 'rainy', 'snow', 'clear', 'overcast']

        for url in sources:
            try:
                if await self._goto(url):
                    content = await self.page.content()
                    for pat in temp_patterns:
                        m = re.findall(pat, content, re.IGNORECASE)
                        if m:
                            data['temperature'] = m[0]
                            data['source'] = url
                            break
                    for kw in condition_kw:
                        if kw in content.lower():
                            data['condition'] = kw
                            break
                    if data['temperature']:
                        break
            except Exception as e:
                print(f"WebAgent: weather error from {url}: {e}")
        return data

    # --- Search (DuckDuckGo + Google fallback) -----------------------------

    async def search(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        results = await self._search_ddg(query, max_results)
        if len(results) < 2:
            results.extend(await self._search_google(query, max_results - len(results)))
        return results

    async def _search_ddg(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        results = []
        try:
            url = f"https://duckduckgo.com/?q={query.replace(' ', '+')}"
            if not await self._goto(url):
                return results
            await asyncio.sleep(2)

            selectors = ["h2 a", "h3 a", ".result__title a", ".result__a",
                         "a[data-testid='result-title']", "a[href*='http']"]

            for sel in selectors:
                try:
                    elements = await self.page.query_selector_all(sel)
                    if not elements:
                        continue
                    for el in elements[:max_results * 2]:
                        try:
                            title = await el.text_content()
                            link = await el.get_attribute("href")
                            if not link or not title:
                                continue
                            skip = ['duckduckgo.com', 'ddg.gg', 'funnel_marketing']
                            if any(s in link.lower() for s in skip):
                                continue
                            if link.startswith('/l/?uddg='):
                                try:
                                    link = unquote(link.split('uddg=')[1])
                                except Exception:
                                    continue
                            if (len(title.strip()) > 10 and link.startswith('http')
                                    and 'duckduckgo.com' not in link.lower()):
                                results.append({'title': title.strip(), 'url': link,
                                                'rank': len(results) + 1, 'source': 'duckduckgo'})
                                if len(results) >= max_results:
                                    break
                        except Exception:
                            continue
                    if results:
                        break
                except Exception:
                    continue
        except Exception as e:
            print(f"WebAgent: DDG search error: {e}")
        return results

    async def _search_google(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        results = []
        try:
            url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
            if await self._goto(url):
                elements = await self.page.query_selector_all("h3")
                for i, el in enumerate(elements[:max_results]):
                    try:
                        title = await el.text_content()
                        if title and len(title.strip()) > 10:
                            results.append({'title': title.strip(), 'url': None,
                                            'rank': i + 1, 'source': 'google'})
                    except Exception:
                        continue
        except Exception as e:
            print(f"WebAgent: Google search error: {e}")
        return results

    # --- Specific data extraction ------------------------------------------

    async def extract_from_url(self, url: str, data_spec: Dict[str, str]) -> Dict[str, Any]:
        extracted = {}
        try:
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            if await self._goto(url):
                for field, selector in data_spec.items():
                    try:
                        el = await self.page.query_selector(selector)
                        if el:
                            val = await el.text_content()
                            extracted[field] = val.strip() if val else None
                        else:
                            extracted[field] = None
                    except Exception:
                        extracted[field] = None
        except Exception as e:
            print(f"WebAgent: extraction error from {url}: {e}")
        return extracted

    # --- AI-powered query processing (requires openai_client) ---------------

    def analyze_query(self, user_query: str) -> Dict[str, Any]:
        if not self.openai_client:
            return {"query_type": "search", "search_strategy": "direct_search",
                    "search_queries": [user_query], "target_sites": [],
                    "data_to_extract": "relevant information",
                    "extraction_method": "search_results"}
        prompt = (
            "Analyze this user query and decide how to extract information.\n"
            f"Query: {user_query}\n"
            "Respond with JSON: {\"query_type\": \"weather|currency|news|search\", "
            "\"search_strategy\": \"direct_search|specific_site|multi_source\", "
            "\"search_queries\": [...], \"target_sites\": [...], "
            "\"data_to_extract\": \"...\", \"extraction_method\": \"search_results|page_content\"}"
        )
        try:
            resp = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You analyze queries for web extraction. Respond JSON only."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=300
            )
            text = resp.choices[0].message.content.strip()
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
        except Exception as e:
            print(f"WebAgent: query analysis error: {e}")

        return {"query_type": "search", "search_strategy": "direct_search",
                "search_queries": [user_query], "target_sites": [],
                "data_to_extract": "relevant information",
                "extraction_method": "search_results"}

    async def process_query(self, user_query: str) -> str:
        """Full AI-powered pipeline: analyze -> search -> extract -> generate response."""
        analysis = self.analyze_query(user_query)
        search_queries = analysis.get("search_queries", [user_query])

        all_results = []
        for q in search_queries[:2]:
            results = await self.search(q)
            all_results.extend(results)
            # Visit top pages for deeper extraction
            for r in results[:2]:
                if r.get('url'):
                    page_data = await self._extract_page_content(r['url'], analysis)
                    all_results.extend(page_data)
            if all_results:
                break

        return self._generate_response(user_query, all_results, analysis)

    async def _extract_page_content(self, url: str, analysis: Dict) -> List[Dict]:
        """Extract content from a page based on query analysis."""
        results = []
        try:
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            if not await self._goto(url):
                return results

            content = await self.page.content()
            data_type = analysis.get("data_to_extract", "").lower()
            query_type = analysis.get("query_type", "").lower()

            patterns = {}
            if "currency" in query_type or "price" in data_type or "exchange" in data_type:
                patterns = {
                    'price': [r'(\d+[.,]\d+)\s*(?:PLN|USD|EUR|CHF|GBP)',
                              r'CHF[:\s]*(\d+[.,]\d+)', r'(\d+[.,]\d+)\s*CHF']
                }
            elif "weather" in query_type or "temperature" in data_type:
                patterns = {'temp': [r'(\d+)\s*°[CF]', r'(\d+)\s*degrees']}
            elif "news" in query_type:
                patterns = {'headline': [r'<h[1-3][^>]*>([^<]+)</h[1-3]>']}

            for label, pats in patterns.items():
                for pat in pats:
                    matches = re.findall(pat, content, re.IGNORECASE)
                    for m in matches[:3]:
                        clean = re.sub(r'<[^>]+>', '', str(m)).strip()
                        if clean:
                            results.append({'title': f"{label}: {clean}", 'url': url,
                                            'rank': len(results) + 1, 'source': 'direct_site'})

            if not results:
                soup = BeautifulSoup(content, 'html.parser')
                lines = [l.strip() for l in soup.get_text().split('\n')
                         if 20 < len(l.strip()) < 200][:3]
                for i, line in enumerate(lines):
                    results.append({'title': line, 'url': url,
                                    'rank': i + 1, 'source': 'direct_site'})
        except Exception as e:
            print(f"WebAgent: page extraction error for {url}: {e}")
        return results

    def _generate_response(self, user_query: str, results: List[Dict], analysis: Dict) -> str:
        if not self.openai_client:
            if results:
                return "; ".join(r['title'] for r in results[:3])
            return "No information found."

        results_text = "\n".join(
            f"{i}. {r['title']}" + (f" ({r['url']})" if r.get('url') else "")
            for i, r in enumerate(results[:5], 1)
        )
        try:
            resp = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system",
                     "content": (f"Provide a concise answer based on search results. "
                                 f"Query type: {analysis.get('query_type', 'search')}. "
                                 f"Keep under 200 chars. Match user's language.")},
                    {"role": "user",
                     "content": f"Query: {user_query}\n\nResults:\n{results_text}"}
                ],
                max_tokens=200
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            print(f"WebAgent: response generation error: {e}")
            if results:
                return results[0]['title']
            return "Could not process query."


# ---------------------------------------------------------------------------
# Synchronous convenience wrappers
# ---------------------------------------------------------------------------

def _run_async(coro):
    """Run an async coroutine synchronously."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def extract_weather_sync(city: str) -> Dict[str, Any]:
    async def _go():
        async with WebAgent() as agent:
            return await agent.extract_weather(city)
    return _run_async(_go())


def search_sync(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    async def _go():
        async with WebAgent() as agent:
            return await agent.search(query, max_results)
    return _run_async(_go())


def extract_specific_data_sync(url: str, data_spec: Dict[str, str]) -> Dict[str, Any]:
    async def _go():
        async with WebAgent() as agent:
            return await agent.extract_from_url(url, data_spec)
    return _run_async(_go())


def process_query_sync(user_query: str, openai_client=None) -> str:
    async def _go():
        async with WebAgent(openai_client=openai_client) as agent:
            return await agent.process_query(user_query)
    return _run_async(_go())


if __name__ == "__main__":
    print("Testing WebAgent...")
    print("\n--- Weather ---")
    w = extract_weather_sync("Zurich")
    print(f"Weather: {w}")
    print("\n--- Search ---")
    r = search_sync("meshtastic firmware update", 3)
    print(f"Results: {r}")
