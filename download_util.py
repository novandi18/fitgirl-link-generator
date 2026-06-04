from playwright.async_api import async_playwright
from playwright_stealth import Stealth
import asyncio
import random
import logging
import re
import requests as req

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Matches both fuckingfast.co/dl/ and dl.fuckingfast.co/dl/ (handles subdomain changes)
DOWNLOAD_LINK_PATTERN = re.compile(r'window\.open\("(https://[^"]*fuckingfast\.co/dl/[^"]+)"')

RATE_LIMIT_KEYWORDS = ('rate limited', 'rate limit', 'too many requests')


async def get_final_download_fuckingfast_async(url: str, max_retries: int = 3) -> str:
    """Get the final download link with retry mechanism for rate limiting"""
    retry_count = 0
    
    while retry_count <= max_retries:
        try:
            if retry_count > 0:
                delay = (2 ** retry_count) + random.uniform(1, 3)
                await asyncio.sleep(delay)
            
            return await _extract_download_link(url)
            
        except RateLimitedException:
            retry_count += 1
            if retry_count <= max_retries:
                logging.info(f"Rate limited. Retrying ({retry_count}/{max_retries}) after backoff...")
            else:
                logging.error("Max retries reached for rate limiting")
                return "Rate limit error - max retries reached"
                
        except Exception as e:
            logging.error(f"Error extracting download link: {str(e)}")
            return f"Error: {str(e)}"
    
    return "Failed after multiple attempts"


class RateLimitedException(Exception):
    """Custom exception for rate limiting detection"""
    pass


def _fetch_page_html(url: str) -> str | None:
    """Fetch page HTML using a plain HTTP request (fast path)"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://fitgirl-repacks.site/',
    }
    try:
        response = req.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            return response.text
    except Exception:
        pass
    return None


async def _extract_download_link(url: str) -> str:
    """Extract download link: tries plain HTTP first, falls back to Playwright"""
    loop = asyncio.get_event_loop()
    html = await loop.run_in_executor(None, _fetch_page_html, url)

    if html:
        lower = html.lower()
        if any(kw in lower for kw in RATE_LIMIT_KEYWORDS):
            raise RateLimitedException("Rate limiting detected")
        match = DOWNLOAD_LINK_PATTERN.search(html)
        if match:
            return match.group(1)

    return await _extract_download_link_playwright(url)


async def _extract_download_link_playwright(url: str) -> str:
    """Fallback: extract download link using Playwright with stealth"""
    async with async_playwright() as p:
        width = random.randint(1280, 1920)
        height = random.randint(800, 1080)
        
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-features=IsolateOrigins,site-per-process'
            ]
        )
        
        context = await browser.new_context(
            viewport={'width': width, 'height': height},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            locale='en-US',
            timezone_id='Europe/London',
            has_touch=False
        )
        
        page = await context.new_page()
        await Stealth().apply_stealth_async(page)
        await asyncio.sleep(random.uniform(0.5, 1.5))
        
        try:
            await page.goto(url, wait_until='networkidle', timeout=60000)
            
            rate_limited = await page.evaluate("""() => {
                return document.body.textContent.includes('rate limited') || 
                    document.body.textContent.includes('Rate Limit') ||
                    document.body.textContent.includes('Too many requests');
            }""")
            
            if rate_limited:
                await browser.close()
                raise RateLimitedException("Rate limiting detected")
            
            await asyncio.sleep(random.uniform(1, 2))

            html = await page.content()
            await browser.close()

            match = DOWNLOAD_LINK_PATTERN.search(html)
            if match:
                return match.group(1)

            return "Download link not found"
            
        except RateLimitedException:
            await browser.close()
            raise
            
        except Exception as e:
            await browser.close()
            raise