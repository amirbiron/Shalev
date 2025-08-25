"""
Stock Scrapers for Israeli Shopping Clubs
Multi-strategy scraping with Playwright, BeautifulSoup, and API calls
"""

import asyncio
import logging
import re
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import aiohttp
import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Browser, Page, TimeoutError as PlaywrightTimeoutError

from config import config, SUPPORTED_CLUBS

logger = logging.getLogger(__name__)

@dataclass
class ProductInfo:
    """Product information structure"""
    name: str
    price: Optional[str]
    in_stock: bool
    stock_text: str
    last_checked: str
    error_message: Optional[str] = None

class StockScraper:
    """Main scraper class supporting multiple scraping strategies"""
    
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Common headers to appear more like a real browser
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0'
        }
        
        # Store-specific configurations
        self.store_configs = SUPPORTED_CLUBS
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.init_browser()
        await self.init_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
    
    async def init_browser(self):
        """Initialize Playwright browser for JS-heavy sites"""
        try:
            self.playwright = await async_playwright().start()
            
            self.browser = await self.playwright.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-accelerated-2d-canvas',
                    '--no-first-run',
                    '--no-zygote',
                    '--single-process',
                    '--disable-gpu'
                ]
            )
            
            logger.info("🌐 Playwright browser initialized")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize browser: {e}")
    
    async def init_session(self):
        """Initialize aiohttp session for HTTP requests"""
        try:
            connector = aiohttp.TCPConnector(
                limit=config.MAX_CONCURRENT_REQUESTS,
                limit_per_host=5,
                ttl_dns_cache=300,
                use_dns_cache=True,
            )
            
            timeout = aiohttp.ClientTimeout(total=config.SCRAPER_TIMEOUT)
            
            self.session = aiohttp.ClientSession(
                headers=self.headers,
                connector=connector,
                timeout=timeout
            )
            
            logger.info("🔗 HTTP session initialized")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize session: {e}")
    
    async def close(self):
        """Clean up resources"""
        if self.session:
            await self.session.close()
        
        if self.browser:
            await self.browser.close()
        
        if hasattr(self, 'playwright'):
            await self.playwright.stop()
    
    async def get_product_info(self, url: str, store_id: str) -> Optional[ProductInfo]:
        """Get comprehensive product information"""
        try:
            store_config = self.store_configs.get(store_id)
            if not store_config:
                logger.error(f"❌ Unknown store: {store_id}")
                return None
            
            logger.info(f"🔍 Getting product info from {store_config['name']}: {url}")
            
            # Prefer lightweight HTTP; fallback to Playwright if needed or required
            requires_js = store_config.get('requires_js', False)

            # First attempt
            first_result: Optional[ProductInfo] = None
            first_error: Optional[Exception] = None
            if not requires_js:
                try:
                    first_result = await self._scrape_with_http(url, store_config)
                except Exception as e:
                    first_error = e
            else:
                try:
                    first_result = await self._scrape_with_playwright(url, store_config)
                except Exception as e:
                    first_error = e

            # If first attempt succeeded with meaningful data, return it
            if first_result and not first_result.error_message and (first_result.name and first_result.name != "לא זמין"):
                return first_result

            # Fallback attempt (swap strategy)
            try:
                if requires_js:
                    # JS required failed or incomplete → try HTTP as fallback
                    return await self._scrape_with_http(url, store_config)
                else:
                    # HTTP failed or incomplete → try Playwright once
                    return await self._scrape_with_playwright(url, store_config)
            except Exception as e:
                logger.error(f"❌ Fallback scraping error: {e}")
                # Return structured error
                return ProductInfo(
                    name="שגיאה בטעינת המוצר",
                    price=None,
                    in_stock=False,
                    stock_text="שגיאה",
                    last_checked="",
                    error_message=str(first_error or e)
                )
                
        except Exception as e:
            logger.error(f"❌ Error getting product info from {url}: {e}")
            return ProductInfo(
                name="שגיאה בטעינת המוצר",
                price=None,
                in_stock=False,
                stock_text="שגיאה",
                last_checked="",
                error_message=str(e)
            )
    
    async def check_stock_status(self, url: str, store_id: str) -> Optional[bool]:
        """Quick stock status check (optimized for frequent checks)"""
        try:
            store_config = self.store_configs.get(store_id)
            if not store_config:
                return None
            
            # Try to extract stock status efficiently
            if store_config.get('requires_js', False):
                return await self._quick_check_with_playwright(url, store_config)
            else:
                return await self._quick_check_with_http(url, store_config)
                
        except Exception as e:
            logger.error(f"❌ Error checking stock status for {url}: {e}")
            return None
    
    async def _scrape_with_playwright(self, url: str, store_config: Dict[str, Any]) -> ProductInfo:
        """Scrape using Playwright for JavaScript-heavy sites"""
        # Ensure browser exists; if closed, re-init
        if not self.browser:
            await self.init_browser()
        
        page = None
        try:
            try:
                page = await self.browser.new_page()
            except Exception as e:
                # Attempt one re-init if browser/page was closed
                if 'has been closed' in str(e).lower() or 'target page' in str(e).lower():
                    logger.warning("🔁 Browser was closed; reinitializing and retrying once...")
                    await self.init_browser()
                    page = await self.browser.new_page()
                else:
                    raise
            
            # Set additional headers if specified
            if 'headers' in store_config:
                await page.set_extra_http_headers(store_config['headers'])
            
            # Navigate to page with timeout
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            
            # Wait for content to load (store-specific)
            await asyncio.sleep(2)
            
            # Extract product information
            product_info = await self._extract_product_info_playwright(page, store_config)
            
            return product_info
            
        except PlaywrightTimeoutError:
            logger.warning(f"⏱️ Timeout loading page: {url}")
            return ProductInfo(
                name="שגיאת זמן קצוב",
                price=None,
                in_stock=False,
                stock_text="שגיאת זמן קצוב",
                last_checked="",
                error_message="Timeout"
            )
        except Exception as e:
            logger.error(f"❌ Playwright scraping error: {e}")
            raise
        finally:
            if page:
                await page.close()
    
    async def _scrape_with_http(self, url: str, store_config: Dict[str, Any]) -> ProductInfo:
        """Scrape using HTTP requests and BeautifulSoup"""
        if not self.session:
            await self.init_session()
        
        try:
            # Prepare headers
            headers = dict(self.headers)
            if 'headers' in store_config:
                headers.update(store_config['headers'])
            
            # Make request
            async with self.session.get(url, headers=headers) as response:
                if response.status != 200:
                    logger.warning(f"⚠️ HTTP {response.status} for {url}")
                    return ProductInfo(
                        name=f"שגיאת HTTP {response.status}",
                        price=None,
                        in_stock=False,
                        stock_text=f"HTTP {response.status}",
                        last_checked="",
                        error_message=f"HTTP {response.status}"
                    )
                
                html = await response.text()
                
            # Parse with BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract product information
            return self._extract_product_info_soup(soup, store_config, url)
            
        except asyncio.TimeoutError:
            logger.warning(f"⏱️ HTTP timeout for {url}")
            return ProductInfo(
                name="שגיאת זמן קצוב",
                price=None,
                in_stock=False,
                stock_text="שגיאת זמן קצוב",
                last_checked="",
                error_message="HTTP Timeout"
            )
        except Exception as e:
            logger.error(f"❌ HTTP scraping error: {e}")
            raise
    
    async def _extract_product_info_playwright(self, page: Page, store_config: Dict[str, Any]) -> ProductInfo:
        """Extract product info from Playwright page"""
        try:
            # Product name
            name_selectors = [
                'h1',
                '.product-title',
                '.product-name',
                '[data-testid="product-title"]',
                '.item-title'
            ]
            
            product_name = "לא זמין"
            for selector in name_selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=5000)
                    if element:
                        product_name = (await element.inner_text()).strip()
                        if product_name:
                            break
                except:
                    continue
            
            # Price
            price_selectors = [
                '.price',
                '.product-price',
                '[data-testid="price"]',
                '.current-price',
                '.final-price'
            ]
            
            price = None
            for selector in price_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        price_text = (await element.inner_text()).strip()
                        if price_text and any(char.isdigit() for char in price_text):
                            price = price_text
                            break
                except:
                    continue
            
            # Stock status
            stock_selector = store_config.get('stock_selector', '.stock-status')
            out_of_stock_indicators = store_config.get('out_of_stock_indicators', ['אזל', 'לא זמין'])
            
            stock_text = ""
            in_stock = True  # Default assumption
            
            try:
                stock_elements = await page.query_selector_all(stock_selector)
                if stock_elements:
                    for element in stock_elements:
                        text = (await element.inner_text()).strip()
                        if text:
                            stock_text = text
                            break
                
                # Check if out of stock
                if stock_text:
                    for indicator in out_of_stock_indicators:
                        if indicator in stock_text:
                            in_stock = False
                            break
                else:
                    # If no stock element found, try alternative methods
                    page_content = await page.content()
                    for indicator in out_of_stock_indicators:
                        if indicator in page_content:
                            in_stock = False
                            stock_text = indicator
                            break
                    
                    if not stock_text:
                        stock_text = "במלאי" if in_stock else "לא זמין"
                        
            except Exception as e:
                logger.warning(f"⚠️ Could not extract stock status: {e}")
                stock_text = "לא ניתן לקבוע"
                in_stock = True  # Assume available if uncertain
            
            return ProductInfo(
                name=product_name,
                price=price,
                in_stock=in_stock,
                stock_text=stock_text,
                last_checked=str(asyncio.get_event_loop().time())
            )
            
        except Exception as e:
            logger.error(f"❌ Error extracting product info with Playwright: {e}")
            raise
    
    def _extract_product_info_soup(self, soup: BeautifulSoup, store_config: Dict[str, Any], url: str) -> ProductInfo:
        """Extract product info from BeautifulSoup object"""
        try:
            # Product name
            name_selectors = [
                'h1',
                '.product-title',
                '.product-name',
                '[data-testid="product-title"]',
                '.item-title'
            ]
            
            product_name = "לא זמין"
            for selector in name_selectors:
                element = soup.select_one(selector)
                if element and element.get_text(strip=True):
                    product_name = element.get_text(strip=True)
                    break
            
            # Price
            price_selectors = [
                '.price',
                '.product-price',
                '[data-testid="price"]',
                '.current-price',
                '.final-price'
            ]
            
            price = None
            for selector in price_selectors:
                element = soup.select_one(selector)
                if element:
                    price_text = element.get_text(strip=True)
                    if price_text and any(char.isdigit() for char in price_text):
                        price = price_text
                        break
            
            # Stock status
            stock_selector = store_config.get('stock_selector', '.stock-status')
            out_of_stock_indicators = store_config.get('out_of_stock_indicators', ['אזל', 'לא זמין'])
            
            stock_text = ""
            in_stock = True  # Default assumption
            
            # Try to find stock element
            stock_elements = soup.select(stock_selector)
            if stock_elements:
                for element in stock_elements:
                    text = element.get_text(strip=True)
                    if text:
                        stock_text = text
                        break
            
            # Check if out of stock
            if stock_text:
                for indicator in out_of_stock_indicators:
                    if indicator in stock_text:
                        in_stock = False
                        break
            else:
                # If no stock element found, search in page content
                page_text = soup.get_text()
                for indicator in out_of_stock_indicators:
                    if indicator in page_text:
                        in_stock = False
                        stock_text = indicator
                        break
                
                if not stock_text:
                    stock_text = "במלאי" if in_stock else "לא זמין"
            
            return ProductInfo(
                name=product_name,
                price=price,
                in_stock=in_stock,
                stock_text=stock_text,
                last_checked=str(asyncio.get_event_loop().time())
            )
            
        except Exception as e:
            logger.error(f"❌ Error extracting product info with BeautifulSoup: {e}")
            raise
    
    async def _quick_check_with_playwright(self, url: str, store_config: Dict[str, Any]) -> Optional[bool]:
        """Quick stock check using Playwright (optimized)"""
        if not self.browser:
            await self.init_browser()
        
        page = None
        try:
            try:
                page = await self.browser.new_page()
            except Exception as e:
                if 'has been closed' in str(e).lower() or 'target page' in str(e).lower():
                    logger.warning("🔁 Browser was closed during quick check; reinitializing...")
                    await self.init_browser()
                    page = await self.browser.new_page()
                else:
                    raise
            
            # Navigate with shorter timeout
            await page.goto(url, wait_until='domcontentloaded', timeout=15000)
            
            # Quick stock status check
            stock_selector = store_config.get('stock_selector', '.stock-status')
            out_of_stock_indicators = store_config.get('out_of_stock_indicators', ['אזל', 'לא זמין'])
            
            # Wait briefly for dynamic content
            await asyncio.sleep(1)
            
            # Check stock status
            try:
                stock_elements = await page.query_selector_all(stock_selector)
                if stock_elements:
                    for element in stock_elements:
                        text = (await element.inner_text()).strip().lower()
                        for indicator in out_of_stock_indicators:
                            if indicator.lower() in text:
                                return False  # Out of stock
                    return True  # In stock
                else:
                    # Fallback to page content search
                    content = await page.content()
                    for indicator in out_of_stock_indicators:
                        if indicator in content:
                            return False
                    return True
                    
            except Exception:
                return None  # Uncertain
                
        except Exception as e:
            logger.warning(f"⚠️ Quick check error with Playwright: {e}")
            return None
        finally:
            if page:
                await page.close()
    
    async def _quick_check_with_http(self, url: str, store_config: Dict[str, Any]) -> Optional[bool]:
        """Quick stock check using HTTP (optimized)"""
        if not self.session:
            await self.init_session()
        
        try:
            # Shorter timeout for quick checks
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    return None
                
                # Read only part of the content for efficiency
                content = ""
                async for chunk in response.content.iter_chunked(8192):
                    content += chunk.decode('utf-8', errors='ignore')
                    # Stop if we have enough content to determine stock status
                    if len(content) > 50000:  # 50KB should be enough
                        break
                
            # Quick text-based check
            out_of_stock_indicators = store_config.get('out_of_stock_indicators', ['אזל', 'לא זמין'])
            
            for indicator in out_of_stock_indicators:
                if indicator in content:
                    return False  # Out of stock
            
            return True  # Assume in stock if no out-of-stock indicators found
            
        except Exception as e:
            logger.warning(f"⚠️ Quick check error with HTTP: {e}")
            return None
    
    # Store-specific optimizations
    async def _check_mashkar_stock(self, url: str) -> Optional[bool]:
        """Optimized stock check for Mashkar (has API)"""
        try:
            # Extract product ID from URL
            product_id = self._extract_mashkar_product_id(url)
            if not product_id:
                return await self._quick_check_with_playwright(url, SUPPORTED_CLUBS['mashkar'])
            
            # Try API endpoint
            api_url = f"https://www.mashkarcard.co.il/api/product/{product_id}/stock"
            
            if not self.session:
                await self.init_session()
            
            async with self.session.get(api_url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('in_stock', False)
                    
        except Exception as e:
            logger.warning(f"⚠️ Mashkar API check failed: {e}")
        
        # Fallback to regular scraping
        return await self._quick_check_with_playwright(url, SUPPORTED_CLUBS['mashkar'])
    
    def _extract_mashkar_product_id(self, url: str) -> Optional[str]:
        """Extract product ID from Mashkar URL"""
        try:
            # Example: https://www.mashkarcard.co.il/product/12345-product-name
            match = re.search(r'/product/(\d+)', url)
            return match.group(1) if match else None
        except:
            return None
    
    # Batch processing utilities
    async def check_multiple_stocks(self, urls_and_stores: List[Tuple[str, str]]) -> Dict[str, Optional[bool]]:
        """Check multiple stocks concurrently"""
        results = {}
        
        # Process in batches to avoid overwhelming servers
        batch_size = min(config.MAX_CONCURRENT_REQUESTS, 5)
        
        for i in range(0, len(urls_and_stores), batch_size):
            batch = urls_and_stores[i:i + batch_size]
            
            tasks = []
            for url, store_id in batch:
                task = self.check_stock_status(url, store_id)
                tasks.append((url, task))
            
            # Execute batch
            batch_results = await asyncio.gather(*[task for _, task in tasks], return_exceptions=True)
            
            # Collect results
            for (url, _), result in zip(batch, batch_results):
                if isinstance(result, Exception):
                    logger.error(f"❌ Batch check error for {url}: {result}")
                    results[url] = None
                else:
                    results[url] = result
            
            # Small delay between batches
            await asyncio.sleep(0.5)
        
        return results
    
    async def get_health_status(self) -> Dict[str, Any]:
        """Get scraper health status"""
        health = {
            'browser_ready': bool(self.browser),
            'session_ready': bool(self.session),
            'supported_stores': len(SUPPORTED_CLUBS),
            'status': 'healthy'
        }
        
        # Test a simple request
        try:
            if self.session:
                async with self.session.get('https://httpbin.org/status/200', timeout=aiohttp.ClientTimeout(total=5)) as response:
                    health['http_test'] = response.status == 200
            else:
                health['http_test'] = False
        except:
            health['http_test'] = False
        
        # Overall health
        if not health['browser_ready'] or not health['session_ready'] or not health['http_test']:
            health['status'] = 'degraded'
        
        return health

# Singleton instance for global use
_scraper_instance: Optional[StockScraper] = None

async def get_scraper() -> StockScraper:
    """Get or create scraper singleton"""
    global _scraper_instance
    
    if _scraper_instance is None:
        _scraper_instance = StockScraper()
        await _scraper_instance.init_browser()
        await _scraper_instance.init_session()
    
    return _scraper_instance

async def cleanup_scraper():
    """Clean up global scraper"""
    global _scraper_instance
    
    if _scraper_instance:
        await _scraper_instance.close()
        _scraper_instance = None
