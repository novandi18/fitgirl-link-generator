from playwright.async_api import async_playwright
from playwright_stealth import Stealth
import asyncio
import random
import logging
import re
import requests as req

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Matches both fuckingfast.co/dl/ and dl.fuckingfast.co/dl/
DOWNLOAD_LINK_PATTERN = re.compile(r'window\.open\(["\'](https://[^"\']*fuckingfast\.co/dl/[^"\']+)["\']')
RATE_LIMIT_KEYWORDS = ('rate limited', 'rate limit', 'too many requests')

# Limit concurrent browser actions to avoid Cloudflare rate limiting
DEFAULT_CONCURRENCY = 2
_SEMAPHORE = asyncio.Semaphore(DEFAULT_CONCURRENCY)


class RateLimitedException(Exception):
    """Custom exception for rate limiting detection"""
    pass


def _fetch_page_html(url: str) -> str | None:
    """Fetch page HTML using a plain HTTP request (legacy fast path)"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://fitgirl-repacks.site/',
    }
    try:
        response = req.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.text
    except Exception:
        pass
    return None


async def extract_download_link_from_page(page, url: str) -> str:
    """Extract direct download link from an open Playwright page, handling HTMX and ad traps."""
    clean_url = url.split('#')[0]
    found_link = None

    def handle_download(d):
        nonlocal found_link
        found_link = d.url

    def handle_popup(p):
        # Auto-close ads and popunders immediately
        asyncio.create_task(p.close())

    async def on_response(response):
        nonlocal found_link
        u = response.url
        if "/dl/" in u:
            found_link = u
        loc = response.headers.get("hx-redirect") or response.headers.get("location")
        if loc and "/dl/" in loc:
            found_link = loc

    page.on("download", handle_download)
    page.on("popup", handle_popup)
    page.on("response", on_response)

    try:
        await page.goto(clean_url, wait_until="load", timeout=30000)
        await asyncio.sleep(1.5)

        # Check for rate limiting
        body_text = await page.evaluate("() => document.body ? document.body.textContent : ''")
        if any(kw in body_text.lower() for kw in RATE_LIMIT_KEYWORDS):
            raise RateLimitedException("Rate limiting detected")

        # Fast check: older mirror using window.open in HTML
        match = DOWNLOAD_LINK_PATTERN.search(body_text)
        if match:
            return match.group(1)

        # Handle the modern HTMX 2-click pattern:
        # Click 1: triggers ad popup (auto-closed by popup listener)
        # Click 2: triggers HTMX POST to /f/<id>/go returning HX-Redirect
        btn = page.locator('a:has-text("DOWNLOAD")')
        if await btn.count() > 0:
            await btn.first.click()
            await asyncio.sleep(0.8)
            await btn.first.click()

            for _ in range(25):
                if found_link:
                    return found_link
                await asyncio.sleep(0.2)

        if found_link:
            return found_link

        return "Download link not found"

    finally:
        page.remove_listener("download", handle_download)
        page.remove_listener("popup", handle_popup)
        page.remove_listener("response", on_response)


async def _extract_download_link_playwright(url: str) -> str:
    """Extract download link using standalone Playwright instance with stealth."""
    async with async_playwright() as p:
        # Try local Chrome first for best stealth, fallback to chromium
        launch_args = ['--disable-blink-features=AutomationControlled', '--no-sandbox']
        try:
            browser = await p.chromium.launch(headless=True, channel="chrome", args=launch_args)
        except Exception:
            browser = await p.chromium.launch(headless=True, args=launch_args)

        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        await Stealth().apply_stealth_async(page)

        try:
            return await extract_download_link_from_page(page, url)
        finally:
            await browser.close()


async def _extract_download_link(url: str) -> str:
    """Extract download link: tries fast HTML regex first, falls back to Playwright."""
    html = await asyncio.get_event_loop().run_in_executor(None, _fetch_page_html, url)
    if html:
        lower = html.lower()
        if any(kw in lower for kw in RATE_LIMIT_KEYWORDS):
            raise RateLimitedException("Rate limiting detected")
        match = DOWNLOAD_LINK_PATTERN.search(html)
        if match:
            return match.group(1)

    return await _extract_download_link_playwright(url)


async def get_final_download_fuckingfast_async(url: str, max_retries: int = 3) -> str:
    """Get the final download link with retry mechanism for rate limiting (bounded concurrency)."""
    async with _SEMAPHORE:
        retry_count = 0
        while retry_count <= max_retries:
            try:
                if retry_count > 0:
                    delay = (2 ** retry_count) + random.uniform(1, 2)
                    await asyncio.sleep(delay)
                return await _extract_download_link(url)

            except RateLimitedException:
                retry_count += 1
                if retry_count <= max_retries:
                    logging.info(f"Rate limited on {url}. Retrying ({retry_count}/{max_retries})...")
                else:
                    logging.error(f"Max retries reached for {url}")
                    return "Rate limit error - max retries reached"

            except Exception as e:
                logging.error(f"Error extracting download link for {url}: {str(e)}")
                return f"Error: {str(e)}"

        return "Failed after multiple attempts"


async def process_fuckingfast_links_batch(links: list[str]) -> list[str]:
    """Efficient batch processor that reuses a single browser session across links."""
    if not links:
        return []

    results = []
    async with async_playwright() as p:
        launch_args = ['--disable-blink-features=AutomationControlled', '--no-sandbox']
        try:
            browser = await p.chromium.launch(headless=True, channel="chrome", args=launch_args)
        except Exception:
            browser = await p.chromium.launch(headless=True, args=launch_args)

        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        await Stealth().apply_stealth_async(page)

        for i, link in enumerate(links, 1):
            logging.info(f"Processing ({i}/{len(links)}): {link}")
            try:
                direct = await extract_download_link_from_page(page, link)
                results.append(direct)
            except Exception as e:
                logging.error(f"Error on {link}: {e}")
                results.append(f"Error: {e}")
            await asyncio.sleep(1.0)

        await browser.close()

    return results