"""
Stock Scrapers for Israeli Shopping Clubs
Multi-strategy scraping with Playwright, BeautifulSoup, and API calls
"""

import asyncio
import logging
import re
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from urllib.parse import urlparse, parse_qs, unquote

import aiohttp
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

    def get_product_key(self, url: str, store_id: str) -> Optional[str]:
        """Return a stable product key for deduplication across URL variants."""
        try:
            parsed = urlparse(url)
            query = parse_qs(parsed.query)

            # Common query identifiers
            if 'ite_item' in query and query['ite_item'] and query['ite_item'][0]:
                return f"ite_item:{query['ite_item'][0]}"
            if 'uuid' in query and query['uuid'] and query['uuid'][0]:
                return f"uuid:{query['uuid'][0]}"

            # Mashkar canonical path id
            if store_id == 'mashkar':
                match = re.search(r'/product/(\d+)', parsed.path)
                if match:
                    return f"id:{match.group(1)}"

            # Generic: last numeric segment
            match = re.search(r'(\d+)', parsed.path)
            if match:
                return f"id:{match.group(1)}"
        except Exception:
            pass
        return None
    
    async def __aenter__(self):
        await self.init_browser()
        await self.init_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def init_browser(self):
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
        if self.session:
            await self.session.close()
        if self.browser:
            await self.browser.close()
        if hasattr(self, 'playwright'):
            await self.playwright.stop()
    
    async def get_product_info(self, url: str, store_id: str) -> Optional[ProductInfo]:
        try:
            store_config = self.store_configs.get(store_id)
            if not store_config:
                logger.error(f"❌ Unknown store: {store_id}")
                return None
            logger.info(f"🔍 Getting product info from {store_config['name']}: {url}")

            requires_js = store_config.get('requires_js', False)

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

            if first_result and not first_result.error_message and (first_result.name and first_result.name != "לא זמין"):
                return first_result

            try:
                if requires_js:
                    return await self._scrape_with_http(url, store_config)
                else:
                    return await self._scrape_with_playwright(url, store_config)
            except Exception as e:
                logger.error(f"❌ Fallback scraping error: {e}")
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
        try:
            store_config = self.store_configs.get(store_id)
            if not store_config:
                return None
            if store_config.get('requires_js', False):
                return await self._quick_check_with_playwright(url, store_config)
            else:
                return await self._quick_check_with_http(url, store_config)
        except Exception as e:
            logger.error(f"❌ Error checking stock status for {url}: {e}")
            return None
    
    async def _scrape_with_playwright(self, url: str, store_config: Dict[str, Any]) -> ProductInfo:
        if not self.browser:
            await self.init_browser()
        page = None
        try:
            try:
                page = await self.browser.new_page()
            except Exception as e:
                if 'has been closed' in str(e).lower() or 'target page' in str(e).lower():
                    logger.warning("🔁 Browser was closed; reinitializing and retrying once...")
                    await self.init_browser()
                    page = await self.browser.new_page()
                else:
                    raise
            if 'headers' in store_config:
                await page.set_extra_http_headers(store_config['headers'])
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            try:
                if 'meshekard.co.il' in url:
                    await asyncio.sleep(1.0)
            except Exception:
                pass
            await asyncio.sleep(2)

            # If site opened a popup window (common in meshekard), use the newest page
            try:
                context_pages = page.context.pages
                content_page = context_pages[-1] if context_pages and context_pages[-1] is not None else page
                if content_page != page:
                    try:
                        await content_page.bring_to_front()
                    except Exception:
                        pass
            except Exception:
                content_page = page

            product_info = await self._extract_product_info_playwright(content_page, store_config, url)
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
        if not self.session:
            await self.init_session()
        try:
            async with self.session.get(url, headers=self.headers) as response:
                if response.status != 200:
                    return ProductInfo(
                        name=f"שגיאת HTTP {response.status}",
                        price=None,
                        in_stock=False,
                        stock_text=f"HTTP {response.status}",
                        last_checked="",
                        error_message=f"HTTP {response.status}"
                    )
                html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')
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
    
    async def _extract_product_info_playwright(self, page: Page, store_config: Dict[str, Any], url: str) -> ProductInfo:
        try:
            product_name = "לא זמין"
            selectors = store_config.get('name_selectors', []) or []
            generic_selectors = [
                '#hdTitle', '#itemTitle', '[id*="lblTitle"]', '[id*="lblItem"]',
                'input#hdTitle', 'input[id*="hdTitle"]', 'input[name*="hdTitle"]',
                'input[id*="ItemName"]', 'input[name*="ItemName"]',
                '.product-title', '.product-name', '.item-title', 'h1'
            ]
            name_selectors = selectors + [s for s in generic_selectors if s not in selectors]

            # Try main page selectors with wait
            for selector in name_selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=1500)
                    if element:
                        candidate = None
                        try:
                            val = await element.get_attribute('value')
                        except Exception:
                            val = None
                        if val and val.strip():
                            candidate = val.strip()
                        else:
                            try:
                                txt = await element.inner_text()
                                txt = (txt or '').strip()
                            except Exception:
                                txt = ''
                            if txt:
                                candidate = txt
                        if not candidate:
                            try:
                                title_attr = await element.get_attribute('title')
                            except Exception:
                                title_attr = None
                            if title_attr and title_attr.strip():
                                candidate = title_attr.strip()
                        if candidate:
                            product_name = candidate
                            break
                except Exception:
                    continue

            # Try frames
            if product_name == "לא זמין":
                try:
                    for frame in page.frames:
                        for selector in name_selectors:
                            try:
                                element = await frame.wait_for_selector(selector, timeout=1500)
                                if element:
                                    candidate = None
                                    try:
                                        val = await element.get_attribute('value')
                                    except Exception:
                                        val = None
                                    if val and val.strip():
                                        candidate = val.strip()
                                    else:
                                        try:
                                            txt = await element.inner_text()
                                            txt = (txt or '').strip()
                                        except Exception:
                                            txt = ''
                                        if txt:
                                            candidate = txt
                                    if not candidate:
                                        try:
                                            title_attr = await element.get_attribute('title')
                                        except Exception:
                                            title_attr = None
                                        if title_attr and title_attr.strip():
                                            candidate = title_attr.strip()
                                    if candidate:
                                        product_name = candidate
                                        raise StopIteration
                            except Exception:
                                continue
                except StopIteration:
                    pass

            # JSON-LD Product (schema.org) and Meta fallbacks
            if product_name == "לא זמין":
                try:
                    scripts = await page.query_selector_all('script[type="application/ld+json"]')
                    for sc in scripts:
                        try:
                            raw = await sc.inner_text()
                            import json
                            data = json.loads(raw)
                            def extract_name(obj: Any) -> Optional[str]:
                                if isinstance(obj, dict):
                                    if obj.get('@type') in ['Product', 'schema:Product'] and isinstance(obj.get('name'), str):
                                        return obj['name']
                                    # common ecommerce nesting
                                    for k in ['item', 'product', 'data']:
                                        if k in obj:
                                            n = extract_name(obj[k])
                                            if n:
                                                return n
                                if isinstance(obj, list):
                                    for it in obj:
                                        n = extract_name(it)
                                        if n:
                                            return n
                                return None
                            name_ld = extract_name(data)
                            if name_ld and name_ld.strip():
                                product_name = name_ld.strip()
                                break
                        except Exception:
                            continue
                except Exception:
                    pass
            if product_name == "לא זמין":
                for meta_sel in ['meta[property="og:title"]', 'meta[name="twitter:title"]', 'meta[name="title"]']:
                    try:
                        meta = await page.query_selector(meta_sel)
                        if meta:
                            content = await meta.get_attribute('content')
                            if content and content.strip():
                                product_name = content.strip()
                                break
                    except Exception:
                        continue

            # Title fallback with sanitization
            if product_name == "לא זמין":
                try:
                    title_text = (await page.title()) or ""
                    title_text = title_text.strip()
                    if title_text:
                        sanitized = self._sanitize_title(title_text, store_config.get('name', ''))
                        if sanitized:
                            product_name = sanitized
                        else:
                            product_name = title_text
                except Exception:
                    pass

            # URL-based guess and Meshkard popup fallback URL
            if self._is_invalid_product_name(product_name, store_config):
                url_guess = self.guess_product_name_from_url(url)
                if url_guess:
                    product_name = url_guess
                # Build a canonical popup URL if only ite_item param exists (legacy meshekard)
                if self._is_invalid_product_name(product_name, store_config):
                    try:
                        parsed = urlparse(url)
                        q = parse_qs(parsed.query)
                        if 'ite_item' in q and q['ite_item'] and q['ite_item'][0]:
                            item_id = q['ite_item'][0]
                            popup_url = f"https://meshekard.co.il/index_popup_meshek.aspx?ite_item={item_id}"
                            # Try navigating the same page to popup URL quickly to read title
                            try:
                                await page.goto(popup_url, wait_until='domcontentloaded', timeout=5000)
                                await asyncio.sleep(1)
                                el = await page.query_selector('#hdTitle, #itemTitle, [id*="lblTitle"], .product-title, h1')
                                if el:
                                    txt = (await el.inner_text()).strip()
                                    if txt:
                                        product_name = txt
                            except Exception:
                                pass
                    except Exception:
                        pass

            # Mashkar API fallback (if still invalid)
            if self._is_invalid_product_name(product_name, store_config) and 'mashkar' in store_config.get('name', '').lower():
                pid = self._extract_mashkar_product_id(url)
                if pid:
                    api_name = await self._fetch_mashkar_product_name_api(pid)
                    if api_name:
                        product_name = api_name
                # Popup HTML fallback via HTTP (safe, no navigation changes)
                if self._is_invalid_product_name(product_name, store_config):
                    try:
                        from urllib.parse import urlparse, parse_qs
                        parsed = urlparse(url)
                        q = parse_qs(parsed.query)
                        if 'ite_item' in q and q['ite_item'] and q['ite_item'][0]:
                            popup_name = await self._fetch_mashkar_popup_name(q['ite_item'][0], store_config)
                            if popup_name:
                                product_name = popup_name
                    except Exception:
                        pass

            # Price (best-effort)
            price = None
            for sel in ['.price', '.product-price', '[data-testid="price"]', '.current-price', '.final-price']:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        price_text = (await el.inner_text()).strip()
                        if price_text and any(ch.isdigit() for ch in price_text):
                            price = price_text
                            break
                except Exception:
                    continue

            # Stock status
            stock_selector = store_config.get('stock_selector', '.stock-status')
            out_of_stock_indicators = store_config.get('out_of_stock_indicators', ['אזל', 'לא זמין'])
            stock_text = ""
            in_stock = True
            try:
                stock_elements = await page.query_selector_all(stock_selector)
                if stock_elements:
                    for el in stock_elements:
                        text = (await el.inner_text()).strip()
                        if text:
                            stock_text = text
                            break
                if stock_text:
                    for indicator in out_of_stock_indicators:
                        if indicator in stock_text:
                            in_stock = False
                            break
                else:
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
                in_stock = True

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
        try:
            product_name = "לא זמין"
            selectors = store_config.get('name_selectors', []) or []
            generic_selectors = [
                '#hdTitle', '#itemTitle', '[id*="lblTitle"]', '[id*="lblItem"]',
                '.product-title', '.product-name', '.item-title', 'h1'
            ]
            name_selectors = selectors + [s for s in generic_selectors if s not in selectors]

            for selector in name_selectors:
                element = soup.select_one(selector)
                if element and element.get_text(strip=True):
                    product_name = element.get_text(strip=True)
                    break

            # JSON-LD Product (schema.org) and Title fallbacks
            if product_name == "לא זמין":
                try:
                    for sc in soup.select('script[type="application/ld+json"]'):
                        import json
                        raw = sc.get_text(strip=True)
                        if not raw:
                            continue
                        data = json.loads(raw)
                        def extract_name(obj: Any) -> Optional[str]:
                            if isinstance(obj, dict):
                                if obj.get('@type') in ['Product', 'schema:Product'] and isinstance(obj.get('name'), str):
                                    return obj['name']
                                for k in ['item', 'product', 'data']:
                                    if k in obj:
                                        n = extract_name(obj[k])
                                        if n:
                                            return n
                            if isinstance(obj, list):
                                for it in obj:
                                    n = extract_name(it)
                                    if n:
                                        return n
                            return None
                        n = extract_name(data)
                        if n and n.strip():
                            product_name = n.strip()
                            break
                except Exception:
                    pass
            if product_name == "לא זמין":
                for meta_sel in ['meta[property="og:title"]', 'meta[name="twitter:title"]', 'meta[name="title"]']:
                    meta = soup.select_one(meta_sel)
                    if meta and meta.get('content') and meta.get('content').strip():
                        product_name = meta.get('content').strip()
                        break
            if product_name == "לא זמין":
                if soup.title and soup.title.get_text(strip=True):
                    title_text = soup.title.get_text(strip=True)
                    sanitized = self._sanitize_title(title_text, store_config.get('name', ''))
                    product_name = sanitized or title_text

            if self._is_invalid_product_name(product_name, store_config):
                url_guess = self.guess_product_name_from_url(url)
                if url_guess:
                    product_name = url_guess

            if self._is_invalid_product_name(product_name, store_config) and 'mashkar' in store_config.get('name', '').lower():
                pid = self._extract_mashkar_product_id(url)
                if pid:
                    # Synchronous path: we do not have await in sync method; leave as-is and keep product_name
                    pass

            price = None
            for sel in ['.price', '.product-price', '[data-testid="price"]', '.current-price', '.final-price']:
                element = soup.select_one(sel)
                if element:
                    price_text = element.get_text(strip=True)
                    if price_text and any(ch.isdigit() for ch in price_text):
                        price = price_text
                        break

            stock_selector = store_config.get('stock_selector', '.stock-status')
            out_of_stock_indicators = store_config.get('out_of_stock_indicators', ['אזל', 'לא זמין'])
            stock_text = ""
            in_stock = True

            stock_elements = soup.select(stock_selector)
            if stock_elements:
                for el in stock_elements:
                    text = el.get_text(strip=True)
                    if text:
                        stock_text = text
                        break
            if stock_text:
                for indicator in out_of_stock_indicators:
                    if indicator in stock_text:
                        in_stock = False
                        break
            else:
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
            await page.goto(url, wait_until='domcontentloaded', timeout=15000)
            stock_selector = store_config.get('stock_selector', '.stock-status')
            out_of_stock_indicators = store_config.get('out_of_stock_indicators', ['אזל', 'לא זמין'])
            await asyncio.sleep(1)
            try:
                stock_elements = await page.query_selector_all(stock_selector)
                if stock_elements:
                    for element in stock_elements:
                        text = (await element.inner_text()).strip().lower()
                        for indicator in out_of_stock_indicators:
                            if indicator.lower() in text:
                                return False
                    return True
                else:
                    content = await page.content()
                    for indicator in out_of_stock_indicators:
                        if indicator in content:
                            return False
                    return True
            except Exception:
                return None
        except Exception as e:
            logger.warning(f"⚠️ Quick check error with Playwright: {e}")
            return None
        finally:
            if page:
                await page.close()

    async def _quick_check_with_http(self, url: str, store_config: Dict[str, Any]) -> Optional[bool]:
        if not self.session:
            await self.init_session()
        try:
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    return None
                content = await response.text()
            out_of_stock_indicators = store_config.get('out_of_stock_indicators', ['אזל', 'לא זמין'])
            for indicator in out_of_stock_indicators:
                if indicator in content:
                    return False
            return True
        except Exception as e:
            logger.warning(f"⚠️ Quick check error with HTTP: {e}")
            return None

    async def _fetch_mashkar_product_name_api(self, product_id: str) -> Optional[str]:
        """Attempt to fetch Mashkar product name from a public API endpoint."""
        try:
            if not self.session:
                await self.init_session()
            for tmpl in [
                f"https://www.mashkarcard.co.il/api/product/{product_id}",
                f"https://www.mashkarcard.co.il/api/products/{product_id}",
            ]:
                try:
                    async with self.session.get(tmpl, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        if resp.status != 200:
                            continue
                        data = await resp.json(content_type=None)
                        # Try common name keys
                        if isinstance(data, dict):
                            for key in ['name', 'title', 'productName', 'ItemName', 'itemName']:
                                if key in data and isinstance(data[key], str) and data[key].strip():
                                    return data[key].strip()
                            # Nested under 'data'
                            inner = data.get('data')
                            if isinstance(inner, dict):
                                for key in ['name', 'title', 'productName', 'ItemName', 'itemName']:
                                    if key in inner and isinstance(inner[key], str) and inner[key].strip():
                                        return inner[key].strip()
                except Exception:
                    continue
        except Exception:
            pass
        return None

    async def _fetch_mashkar_popup_name(self, item_id: str, store_config: Dict[str, Any]) -> Optional[str]:
        """Fetch and parse the Mashkar popup HTML to extract the product name."""
        try:
            if not self.session:
                await self.init_session()
            headers = dict(self.headers)
            if 'headers' in store_config:
                headers.update(store_config['headers'])
            popup_hosts = [
                'meshekard.co.il', 'www.meshekard.co.il',
                'mashkarcard.co.il', 'www.mashkarcard.co.il'
            ]
            for host in popup_hosts:
                url = f"https://{host}/index_popup_meshek.aspx?ite_item={item_id}"
                try:
                    timeout = aiohttp.ClientTimeout(total=8)
                    async with self.session.get(url, headers=headers, timeout=timeout) as resp:
                        if resp.status != 200:
                            continue
                        html = await resp.text()
                        soup = BeautifulSoup(html, 'html.parser')
                        selectors = store_config.get('name_selectors', []) or []
                        generic = ['#hdTitle', '#itemTitle', '[id*="lblTitle"]', '[id*="lblItem"]', '.product-title', '.item-title', 'h1']
                        for sel in selectors + [s for s in generic if s not in selectors]:
                            el = soup.select_one(sel)
                            if el and el.get_text(strip=True):
                                name = el.get_text(strip=True)
                                if name and name not in {store_config.get('name', '').strip()}:
                                    return name
                except Exception:
                    continue
        except Exception:
            pass
        return None

    async def _check_mashkar_stock(self, url: str) -> Optional[bool]:
        try:
            product_id = self._extract_mashkar_product_id(url)
            if not product_id:
                return await self._quick_check_with_playwright(url, SUPPORTED_CLUBS['mashkar'])
            api_url = f"https://www.mashkarcard.co.il/api/product/{product_id}/stock"
            if not self.session:
                await self.init_session()
            async with self.session.get(api_url) as response:
                if response.status == 200:
                    data = await response.json(content_type=None)
                    return data.get('in_stock', False)
        except Exception as e:
            logger.warning(f"⚠️ Mashkar API check failed: {e}")
        return await self._quick_check_with_playwright(url, SUPPORTED_CLUBS['mashkar'])
    
    def _extract_mashkar_product_id(self, url: str) -> Optional[str]:
        try:
            match = re.search(r'/product/(\d+)', url)
            return match.group(1) if match else None
        except Exception:
            return None

    def _is_invalid_product_name(self, name: Optional[str], store_config: Dict[str, Any]) -> bool:
        try:
            if not name:
                return True
            normalized = re.sub(r"\s+", " ", str(name)).strip().strip('"\'')
            if not normalized:
                return True
            if normalized in {"לא זמין", store_config.get('name', '').strip()}:
                return True
            if len(normalized) < 3:
                return True
            return False
        except Exception:
            return False

    def _sanitize_title(self, title: str, store_name: str) -> Optional[str]:
        try:
            t = (title or '').strip()
            s = (store_name or '').strip()
            if not t:
                return None
            # Remove store name and common separators
            for sep in [' - ', ' | ', ' – ', ' — ']:
                if s and sep in t:
                    parts = [p.strip() for p in t.split(sep) if p.strip()]
                    # remove pure store name chunks
                    parts = [p for p in parts if p != s]
                    if parts:
                        return parts[0] if len(parts) == 1 else ' '.join(parts)
            if s and t == s:
                return None
            return t
        except Exception:
            return None

    def guess_product_name_from_url(self, url: str) -> Optional[str]:
        try:
            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            for key in ("title", "name", "item_name", "ite_text"):
                if key in query and query[key] and query[key][0]:
                    val = unquote(query[key][0])
                    val = val.replace('-', ' ').replace('_', ' ').strip().strip('"\'')
                    if len(val) >= 3:
                        return val
            path = parsed.path or ""
            m = re.search(r"/product/([^/?#]+)", path, re.IGNORECASE)
            if m:
                segment = m.group(1)
                segment = re.sub(r"^\d+[-_]?", "", segment)
                segment = unquote(segment)
                candidate = segment.replace('-', ' ').replace('_', ' ').strip().strip('"\'')
                if len(candidate) >= 3 and any(ch.isalpha() for ch in candidate):
                    return candidate
        except Exception:
            pass
        return None

    async def check_multiple_stocks(self, urls_and_stores: List[Tuple[str, str]]) -> Dict[str, Optional[bool]]:
        results = {}
        batch_size = min(config.MAX_CONCURRENT_REQUESTS, 5)
        for i in range(0, len(urls_and_stores), batch_size):
            batch = urls_and_stores[i:i + batch_size]
            tasks = []
            for url, store_id in batch:
                task = self.check_stock_status(url, store_id)
                tasks.append((url, task))
            batch_results = await asyncio.gather(*[task for _, task in tasks], return_exceptions=True)
            for (url, _), result in zip(batch, batch_results):
                if isinstance(result, Exception):
                    logger.error(f"❌ Batch check error for {url}: {result}")
                    results[url] = None
                else:
                    results[url] = result
            await asyncio.sleep(0.5)
        return results

    async def get_health_status(self) -> Dict[str, Any]:
        health = {
            'browser_ready': bool(self.browser),
            'session_ready': bool(self.session),
            'supported_stores': len(SUPPORTED_CLUBS),
            'status': 'healthy'
        }
        try:
            if self.session:
                async with self.session.get('https://httpbin.org/status/200', timeout=aiohttp.ClientTimeout(total=5)) as response:
                    health['http_test'] = response.status == 200
            else:
                health['http_test'] = False
        except Exception:
            health['http_test'] = False
        if not health['browser_ready'] or not health['session_ready'] or not health['http_test']:
            health['status'] = 'degraded'
        return health

_scraper_instance: Optional[StockScraper] = None

async def get_scraper() -> StockScraper:
    global _scraper_instance
    if _scraper_instance is None:
        _scraper_instance = StockScraper()
        await _scraper_instance.init_browser()
        await _scraper_instance.init_session()
    return _scraper_instance

async def cleanup_scraper():
    global _scraper_instance
    if _scraper_instance:
        await _scraper_instance.close()
        _scraper_instance = None