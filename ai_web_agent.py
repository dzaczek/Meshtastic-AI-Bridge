# ai_web_agent.py
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
# Remove direct OpenAI import to avoid import issues
# from openai import OpenAI
import base64

class AIWebAgent:
    """
    AI-powered web agent that decides how to extract information from the web
    """
    
    def __init__(self, openai_client, timeout_s=30):
        self.openai_client = openai_client
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
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 AIWebAgent/1.0",
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
            await asyncio.sleep(3)  # Allow JS to load
            return True
        except Exception as e:
            print(f"Error navigating to {url}: {e}")
            return False

    def analyze_query(self, user_query: str) -> Dict[str, Any]:
        """Use AI to analyze the query and decide how to extract information"""
        if not self.openai_client:
            return {"error": "OpenAI client not available"}
            
        system_prompt = """
        You are an AI web agent that analyzes user queries and decides how to extract information from the web.
        
        For each query, determine:
        1. Query type: weather, currency, news, search, specific_data
        2. Search strategy: direct_search, specific_site, multi_source
        3. Search queries: list of search terms to use
        4. Target sites: specific websites to check (if applicable)
        5. Data to extract: what specific information to look for
        
        Respond with JSON format:
        {
            "query_type": "weather|currency|news|search|specific_data",
            "search_strategy": "direct_search|specific_site|multi_source",
            "search_queries": ["query1", "query2"],
            "target_sites": ["site1.com", "site2.com"],
            "data_to_extract": "temperature, price, title, etc.",
            "extraction_method": "search_results|page_content|specific_element"
        }
        """
        
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Analyze this query: {user_query}"}
                ],
                max_tokens=300
            )
            
            result = response.choices[0].message.content.strip()
            # Try to parse JSON
            try:
                return json.loads(result)
            except json.JSONDecodeError:
                # Fallback if AI doesn't return valid JSON
                return {
                    "query_type": "search",
                    "search_strategy": "direct_search",
                    "search_queries": [user_query],
                    "target_sites": [],
                    "data_to_extract": "relevant information",
                    "extraction_method": "search_results"
                }
                
        except Exception as e:
            print(f"Error analyzing query: {e}")
            return {"error": str(e)}

    async def execute_search_strategy(self, analysis: Dict[str, Any]) -> List[Dict[str, str]]:
        """Execute the search strategy determined by AI"""
        results = []
        
        if analysis.get("error"):
            return results
            
        search_strategy = analysis.get("search_strategy", "direct_search")
        search_queries = analysis.get("search_queries", [])
        
        if search_strategy == "direct_search":
            # Use multiple search engines
            for query in search_queries:
                # Try DuckDuckGo first
                ddg_results = await self.search_duckduckgo(query)
                
                # If DuckDuckGo found good results, use them
                if ddg_results and len(ddg_results) >= 2:
                    results.extend(ddg_results)
                    print(f"INFO: Using {len(ddg_results)} DuckDuckGo results")
                else:
                    # Try Google if DuckDuckGo failed or found too few results
                    print(f"INFO: DuckDuckGo found only {len(ddg_results) if ddg_results else 0} results, trying Google...")
                    google_results = await self.search_google(query)
                    if google_results:
                        results.extend(google_results)
                        print(f"INFO: Using {len(google_results)} Google results")
                    elif ddg_results:
                        # Use whatever DuckDuckGo found
                        results.extend(ddg_results)
                        print(f"INFO: Using {len(ddg_results)} DuckDuckGo results as fallback")
                    
                # If we found search results, visit the top 2-3 pages and extract data
                if results:
                    print(f"INFO: Found {len(results)} search results, visiting top pages to extract data...")
                    visited_results = []
                    for result in results[:3]:  # Visit top 3 results
                        if result.get('url'):
                            print(f"INFO: Visiting {result['url']} to extract data...")
                            page_data = await self.extract_from_site(result['url'], analysis)
                            if page_data:
                                visited_results.extend(page_data)
                                print(f"INFO: Extracted {len(page_data)} data points from {result['url']}")
                            else:
                                print(f"INFO: No data extracted from {result['url']}")
                    # Replace search results with extracted data
                    if visited_results:
                        results = visited_results
                        print(f"INFO: Total extracted data points: {len(results)}")
                    break  # Stop after first successful query
        elif search_strategy == "specific_site":
            # Go directly to specific sites
            target_sites = analysis.get("target_sites", [])
            for site in target_sites:
                site_results = await self.extract_from_site(site, analysis)
                results.extend(site_results)
                
        elif search_strategy == "multi_source":
            # Combine search and specific sites
            for query in search_queries:
                search_results = await self.search_duckduckgo(query)
                results.extend(search_results)
                
            target_sites = analysis.get("target_sites", [])
            for site in target_sites:
                site_results = await self.extract_from_site(site, analysis)
                results.extend(site_results)
                
        return results

    async def search_duckduckgo(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        """Search DuckDuckGo and extract results"""
        results = []
        try:
            search_url = f"https://duckduckgo.com/?q={query.replace(' ', '+')}"
            if await self.navigate_to_page(search_url):
                # Wait a bit more for results to load
                await asyncio.sleep(2)
                
                # Extract search results - try different selectors
                selectors_to_try = [
                    "h2 a",  # Most common for DuckDuckGo
                    "h3 a", 
                    ".result__title a",
                    ".result__a",
                    "a[data-testid='result-title']",
                    "a[href*='http']"  # Any link with http
                ]
                
                for selector in selectors_to_try:
                    try:
                        result_elements = await self.page.query_selector_all(selector)
                        if result_elements:
                            for i, element in enumerate(result_elements[:max_results * 2]):  # Get more to filter
                                try:
                                    title = await element.text_content()
                                    link = await element.get_attribute("href")
                                    
                                    # Skip marketing/own pages
                                    if any(skip in link.lower() for skip in [
                                        'duckduckgo.com', 'ddg.gg', 'funnel_marketing', 
                                        'windows', 'mac', 'android', 'ios', 'browser'
                                    ]):
                                        continue
                                    
                                    # Clean up the link (remove redirects)
                                    if link and link.startswith('/l/?uddg='):
                                        # DuckDuckGo redirect link, try to extract real URL
                                        try:
                                            from urllib.parse import unquote
                                            real_url = unquote(link.split('uddg=')[1])
                                            link = real_url
                                        except:
                                            continue
                                    
                                    if title and len(title.strip()) > 10 and link and link.startswith('http'):
                                        # Skip if it's still a DuckDuckGo link after cleanup
                                        if 'duckduckgo.com' in link.lower():
                                            continue
                                            
                                        results.append({
                                            'title': title.strip(),
                                            'url': link,
                                            'rank': i + 1,
                                            'source': 'duckduckgo'
                                        })
                                        print(f"INFO: Found result: {title[:50]}... -> {link}")
                                        
                                        if len(results) >= max_results:
                                            break
                                except Exception as e:
                                    continue
                            if results:
                                break
                    except Exception as e:
                        continue
                        
        except Exception as e:
            print(f"Error searching DuckDuckGo: {e}")
            
        return results

    async def search_google(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        """Search Google and extract results"""
        results = []
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
                                'rank': i + 1,
                                'source': 'google'
                            })
                    except Exception as e:
                        continue
                        
        except Exception as e:
            print(f"Error searching Google: {e}")
            
        return results

    async def extract_from_site(self, url: str, analysis: Dict[str, Any]) -> List[Dict[str, str]]:
        """Extract specific information from a site based on AI analysis"""
        results = []
        try:
            # Fix URL if it doesn't have protocol
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
                print(f"INFO: Fixed URL to {url}")
                
            if await self.navigate_to_page(url):
                # Get page content
                content = await self.page.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                # Extract relevant information based on analysis
                data_to_extract = analysis.get("data_to_extract", "")
                query_type = analysis.get("query_type", "")
                
                print(f"INFO: Extracting {data_to_extract} from {url}")
                
                if "currency" in query_type.lower() or "price" in data_to_extract.lower() or "exchange" in data_to_extract.lower():
                    # Look for currency/price patterns
                    price_patterns = [
                        r'(\d+[.,]\d+)\s*(?:PLN|USD|EUR|CHF|GBP)',  # 4.12 PLN
                        r'(\d+[.,]\d+)\s*zł',  # 4.12 zł
                        r'(\d+[.,]\d+)\s*euro',  # 1.23 euro
                        r'(\d+[.,]\d+)\s*frank',  # 1.23 frank
                        r'CHF[:\s]*(\d+[.,]\d+)',  # CHF: 1.23
                        r'(\d+[.,]\d+)\s*CHF',  # 1.23 CHF
                        r'(\d+[.,]\d+)\s*USD',  # 1.23 USD
                        r'(\d+[.,]\d+)\s*EUR',  # 1.23 EUR
                    ]
                    
                    for pattern in price_patterns:
                        matches = re.findall(pattern, content, re.IGNORECASE)
                        if matches:
                            for match in matches[:3]:  # Take first 3 matches
                                results.append({
                                    'title': f"Exchange rate: {match}",
                                    'url': url,
                                    'rank': len(results) + 1,
                                    'source': 'direct_site'
                                })
                                print(f"INFO: Found exchange rate: {match}")
                    
                    # Also look for specific currency pairs
                    currency_patterns = [
                        r'CHF/PLN[:\s]*(\d+[.,]\d+)',
                        r'PLN/CHF[:\s]*(\d+[.,]\d+)',
                        r'USD/CHF[:\s]*(\d+[.,]\d+)',
                        r'CHF/USD[:\s]*(\d+[.,]\d+)',
                        r'EUR/CHF[:\s]*(\d+[.,]\d+)',
                        r'CHF/EUR[:\s]*(\d+[.,]\d+)',
                    ]
                    
                    for pattern in currency_patterns:
                        matches = re.findall(pattern, content, re.IGNORECASE)
                        if matches:
                            for match in matches[:2]:  # Take first 2 matches
                                results.append({
                                    'title': f"Currency pair: {pattern.split('[')[0]}{match}",
                                    'url': url,
                                    'rank': len(results) + 1,
                                    'source': 'direct_site'
                                })
                                print(f"INFO: Found currency pair: {pattern.split('[')[0]}{match}")
                                
                elif "news" in query_type.lower() or "headlines" in data_to_extract.lower():
                    # Look for news headlines and articles
                    news_patterns = [
                        r'<h[1-3][^>]*>([^<]+)</h[1-3]>',  # Headlines in h1-h3 tags
                        r'<title>([^<]+)</title>',  # Page title
                        r'<article[^>]*>.*?<h[1-3][^>]*>([^<]+)</h[1-3]>',  # Article headlines
                    ]
                    
                    for pattern in news_patterns:
                        matches = re.findall(pattern, content, re.IGNORECASE | re.DOTALL)
                        if matches:
                            for match in matches[:5]:  # Take first 5 matches
                                clean_title = re.sub(r'<[^>]+>', '', match).strip()
                                if len(clean_title) > 10 and len(clean_title) < 200:
                                    results.append({
                                        'title': f"News: {clean_title}",
                                        'url': url,
                                        'rank': len(results) + 1,
                                        'source': 'direct_site'
                                    })
                                    print(f"INFO: Found news: {clean_title[:50]}...")
                                    
                elif "temperature" in data_to_extract.lower() or "weather" in query_type.lower():
                    # Look for temperature patterns
                    temp_patterns = [
                        r'(\d+)\s*°[CF]',  # 25°C or 77°F
                        r'(\d+)\s*degrees',  # 25 degrees
                        r'temperature[:\s]*(\d+)',  # temperature: 25
                        r'(\d+)\s*°C',  # 25°C
                        r'(\d+)\s*°F',  # 77°F
                    ]
                    
                    for pattern in temp_patterns:
                        matches = re.findall(pattern, content, re.IGNORECASE)
                        if matches:
                            for match in matches[:2]:  # Take first 2 matches
                                results.append({
                                    'title': f"Temperature: {match}°",
                                    'url': url,
                                    'rank': len(results) + 1,
                                    'source': 'direct_site'
                                })
                                print(f"INFO: Found temperature: {match}°")
                                
                # If no specific patterns found, extract general content
                if not results:
                    text_content = soup.get_text()
                    lines = text_content.split('\n')
                    relevant_lines = [line.strip() for line in lines if len(line.strip()) > 20 and len(line.strip()) < 200][:3]
                    
                    for i, line in enumerate(relevant_lines):
                        results.append({
                            'title': line,
                            'url': url,
                            'rank': i + 1,
                            'source': 'direct_site'
                        })
                        print(f"INFO: Found general content: {line[:50]}...")
                        
        except Exception as e:
            print(f"Error extracting from site {url}: {e}")
            
        return results

    def generate_response(self, user_query: str, search_results: List[Dict[str, str]], analysis: Dict[str, Any]) -> str:
        """Use AI to generate a response based on search results"""
        if not self.openai_client:
            return "Unable to generate response - AI client not available"
            
        # Format search results for AI
        results_text = ""
        for i, result in enumerate(search_results[:5], 1):
            results_text += f"{i}. {result['title']}"
            if result.get('url'):
                results_text += f" ({result['url']})"
            results_text += f" [Source: {result.get('source', 'unknown')}]\n"
            
        system_prompt = f"""
        You are an AI assistant that provides information based on web search results.
        
        Query type: {analysis.get('query_type', 'unknown')}
        Data to extract: {analysis.get('data_to_extract', 'relevant information')}
        
        Provide a concise, helpful response based on the search results. 
        If you found specific data (like temperature, price, etc.), include it in your response.
        If the results are not relevant or insufficient, explain what you found and suggest alternatives.
        
        Keep your response under 200 characters and in the same language as the user's query.
        """
        
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"User query: {user_query}\n\nSearch results:\n{results_text}"}
                ],
                max_tokens=200
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            print(f"Error generating response: {e}")
            return f"Found some information but couldn't process it properly: {results_text[:100]}..."

    async def process_query(self, user_query: str) -> str:
        """Main method to process a user query and return a response"""
        try:
            # Step 1: Analyze the query
            print(f"INFO: Analyzing query: {user_query}")
            analysis = self.analyze_query(user_query)
            print(f"INFO: Analysis result: {analysis}")
            
            # Step 2: Execute search strategy
            print(f"INFO: Executing search strategy: {analysis.get('search_strategy')}")
            search_results = await self.execute_search_strategy(analysis)
            print(f"INFO: Found {len(search_results)} results")
            
            # Step 3: Generate response
            print(f"INFO: Generating response")
            response = self.generate_response(user_query, search_results, analysis)
            
            return response
            
        except Exception as e:
            print(f"Error processing query: {e}")
            return f"Sorry, I encountered an error while processing your query: {str(e)}"

# Convenience function for synchronous use
def process_query_sync(user_query: str, openai_client) -> str:
    """Synchronous wrapper for process_query"""
    async def _process_query():
        async with AIWebAgent(openai_client) as agent:
            return await agent.process_query(user_query)
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(_process_query())
    finally:
        loop.close()

if __name__ == "__main__":
    # Test the AI web agent
    print("Testing AI Web Agent...")
    
    # You would need to initialize OpenAI client here
    # openai_client = OpenAI(api_key="your-api-key")
    # result = process_query_sync("jaka jest pogoda w Zurich", openai_client)
    # print(f"Result: {result}") 