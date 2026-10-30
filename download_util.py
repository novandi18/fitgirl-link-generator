from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from urllib.parse import urljoin
import asyncio
import random
import logging
import re
import requests as req

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Matches both fuckingfast.co/dl/ and dl.fuckingfast.co/dl/
DOWNLOAD_LINK_PATTERN = re.compile(r'window\.open\(["\'](https://[^"\']*fuckingfast\.co/dl/[^"\']+)["\']')
RATE_LIMIT_KEYWORDS = ('rate limited', 'rate limit', 'too many requests')

# Default parallel browser tabs (balanced for speed vs Cloudflare/FuckingFast rate limits)
DEFAULT_CONCURRENCY = 3
_SEMAPHORE: asyncio.Semaphore | None = None

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class RateLimitedException(Exception):
    """Custom exception for rate limiting detection"""
    pass


def is_valid_direct_link(link: str | None) -> bool:
    """Return True if the extracted result is a usable direct download URL."""
    if not link or not isinstance(link, str):
        return False
    if (
        link.startswith("Error:")
        or link == "Download link not found"
        or "Rate limit error" in link
        or link == "Failed after multiple attempts"
    ):
        return False
    return link.startswith("http")


def sort_fuckingfast_links(links: list[str]) -> list[str]:
    """
    Deduplicate and naturally sort FuckingFast links so multi-part archives
    (e.g. part1.rar .. part8.rar .. part10.rar) stay strictly in part order.
    Links without a #filename fragment preserve their original relative order.
    """
    seen = set()
    unique_links: list[str] = []
    for link in links:
        base = link.split('#', 1)[0].strip()
        if base and base not in seen:
            seen.add(base)
            unique_links.append(link.strip())

    def _sort_key(item: tuple[int, str]):
        idx, url = item
        if '#' not in url:
            return (3, [], idx)
        fragment = url.split('#', 1)[1].strip()
        if not fragment:
            return (3, [], idx)

        lower_frag = fragment.lower()
        if 'fg-optional' in lower_frag:
            category = 2
        elif 'fg-selective' in lower_frag:
            category = 1
        else:
            category = 0

        # Tuple-tag ints vs strings to prevent TypeError during comparison in Python 3
        natural_parts = [
            (0, int(tok)) if tok.isdigit() else (1, tok)
            for tok in re.split(r'(\d+)', lower_frag)
            if tok
        ]
        return (category, natural_parts, idx)

    indexed = list(enumerate(unique_links))
    indexed.sort(key=_sort_key)
    return [url for _, url in indexed]


def _fetch_page_html(url: str) -> str | None:
    """Fetch page HTML using a plain HTTP request (legacy fast path)"""
    headers = {
        'User-Agent': USER_AGENT,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://fitgirl-repacks.site/',
    }
    try:
        response = req.get(url.split('#')[0], headers=headers, timeout=10)
        if response.status_code == 200:
            return response.text
    except Exception:
        pass
    return None


async def extract_download_link_from_page(page, url: str) -> str:
    """Extract direct download link from an open Playwright page, handling HTMX and ad traps."""
    clean_url = url.split('#')[0]
    found_link: str | None = None
    link_event = asyncio.Event()

    def _set_found(candidate: str):
        nonlocal found_link
        if not found_link and candidate:
            found_link = candidate
            link_event.set()

    async def _safe_cancel_download(download):
        try:
            await download.cancel()
        except Exception:
            pass

    async def _safe_close_popup(popup):
        try:
            await popup.close()
        except Exception:
            pass

    def handle_download(download):
        _set_found(download.url)
        # Cancel browser file transfer immediately; we only need the direct URL
        asyncio.create_task(_safe_cancel_download(download))

    def handle_popup(popup):
        # Auto-close ads and popunders immediately
        asyncio.create_task(_safe_close_popup(popup))

    def on_response(response):
        u = response.url
        if "/dl/" in u:
            _set_found(u)
            return
        headers = response.headers
        loc = headers.get("hx-redirect") or headers.get("location")
        if loc and "/dl/" in loc:
            _set_found(urljoin(clean_url, loc))

    page.on("download", handle_download)
    page.on("popup", handle_popup)
    page.on("response", on_response)

    try:
        try:
            response = await page.goto(clean_url, wait_until="load", timeout=30000)
            if response and response.status == 429:
                raise RateLimitedException("HTTP 429 Too Many Requests")
        except RateLimitedException:
            raise
        except Exception:
            if found_link:
                return found_link
            # If load timed out due to slow third-party ad assets, continue if DOM exists
            has_dom = await page.evaluate("() => Boolean(document.body)")
            if not has_dom:
                raise

        await asyncio.sleep(1.2)

        if found_link:
            return found_link

        # Check for rate limiting
        body_text = await page.evaluate("() => document.body ? document.body.textContent : ''")
        if any(kw in body_text.lower() for kw in RATE_LIMIT_KEYWORDS):
            raise RateLimitedException("Rate limiting detected")

        # Fast check: older mirror using window.open in HTML source
        html_content = await page.content()
        match = DOWNLOAD_LINK_PATTERN.search(html_content)
        if match:
            return match.group(1)

        # Handle the modern HTMX 2-click pattern:
        # Click 1: triggers ad popup (auto-closed by popup listener)
        # Click 2: triggers HTMX POST to /f/<id>/go returning HX-Redirect
        btn = page.locator('a:has-text("DOWNLOAD"), button:has-text("DOWNLOAD")')
        if await btn.count() > 0:
            await btn.first.click(timeout=5000)
            try:
                await asyncio.wait_for(link_event.wait(), timeout=0.8)
                if found_link:
                    return found_link
            except asyncio.TimeoutError:
                pass

            if not found_link and await btn.count() > 0:
                await btn.first.click(timeout=5000)
                try:
                    await asyncio.wait_for(link_event.wait(), timeout=6.0)
                    if found_link:
                        return found_link
                except asyncio.TimeoutError:
                    pass

        if found_link:
            return found_link

        # Re-check rate limit in case HTMX injected a rate-limit message
        body_text_after = await page.evaluate("() => document.body ? document.body.textContent : ''")
        if any(kw in body_text_after.lower() for kw in RATE_LIMIT_KEYWORDS):
            raise RateLimitedException("Rate limiting detected after click")

        return "Download link not found"

    except RateLimitedException:
        raise
    except Exception:
        if found_link:
            return found_link
        raise
    finally:
        page.remove_listener("download", handle_download)
        page.remove_listener("popup", handle_popup)
        page.remove_listener("response", on_response)


class FuckingFastBatchExtractor:
    """
    Async batch extractor using a reusable stealth browser context and a pool
    of concurrent tabs while preserving exact input-to-output link ordering.
    """

    def __init__(self, concurrency: int = DEFAULT_CONCURRENCY, max_retries: int = 3):
        self.concurrency = max(1, concurrency)
        self.max_retries = max(0, max_retries)
        self._playwright = None
        self._browser = None
        self._context = None
        self._pages: list = []
        self._page_queue: asyncio.Queue | None = None

    async def __aenter__(self):
        self._playwright = await async_playwright().start()
        launch_args = ['--disable-blink-features=AutomationControlled', '--no-sandbox']
        try:
            self._browser = await self._playwright.chromium.launch(
                headless=True, channel="chrome", args=launch_args
            )
        except Exception:
            self._browser = await self._playwright.chromium.launch(
                headless=True, args=launch_args
            )

        self._context = await self._browser.new_context(
            user_agent=USER_AGENT,
            accept_downloads=True,
        )
        self._pages = []
        self._page_queue = asyncio.Queue()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass

    async def _create_stealth_page(self):
        page = await self._context.new_page()
        await Stealth().apply_stealth_async(page)
        return page

    async def _ensure_pool(self, total_links: int):
        target_size = min(self.concurrency, total_links)
        while len(self._pages) < target_size:
            page = await self._create_stealth_page()
            self._pages.append(page)
            self._page_queue.put_nowait(page)

    async def _reset_or_replace_page(self, page):
        if not page.is_closed():
            try:
                await page.goto("about:blank", timeout=5000)
                return page
            except Exception:
                try:
                    await page.close()
                except Exception:
                    pass
        if page in self._pages:
            self._pages.remove(page)
        new_page = await self._create_stealth_page()
        self._pages.append(new_page)
        return new_page

    async def process_links(self, links: list[str]) -> list[str]:
        """
        Extract direct download URLs concurrently across pooled tabs.
        Returns results strictly aligned with the input `links` order.
        """
        if not links:
            return []

        await self._ensure_pool(len(links))
        total = len(links)
        completed = 0

        async def _process_one(idx: int, link: str) -> str:
            nonlocal completed
            label = link.split('#', 1)[1] if '#' in link else link
            page = await self._page_queue.get()

            try:
                # Slight stagger to prevent simultaneous burst requests
                await asyncio.sleep(random.uniform(0.15, 0.5))

                for attempt in range(self.max_retries + 1):
                    try:
                        logging.info(f"[Part {idx + 1}/{total}] Extracting: {label}")
                        direct = await extract_download_link_from_page(page, link)
                        page = await self._reset_or_replace_page(page)

                        if is_valid_direct_link(direct):
                            completed += 1
                            logging.info(f"[{completed}/{total} done] Part {idx + 1} OK: {label}")
                            return direct

                        if attempt < self.max_retries:
                            delay = (2 ** (attempt + 1)) + random.uniform(0.5, 1.5)
                            logging.warning(
                                f"[Part {idx + 1}/{total}] Link not found for {label}. "
                                f"Retrying ({attempt + 1}/{self.max_retries}) in {delay:.1f}s..."
                            )
                            await asyncio.sleep(delay)
                        else:
                            completed += 1
                            logging.error(f"[{completed}/{total} done] Part {idx + 1} FAILED (not found): {label}")
                            return "Download link not found"

                    except RateLimitedException:
                        page = await self._reset_or_replace_page(page)
                        if attempt < self.max_retries:
                            delay = (2 ** (attempt + 1)) + random.uniform(1.5, 3.0)
                            logging.warning(
                                f"[Part {idx + 1}/{total}] Rate limited on {label}. "
                                f"Retrying ({attempt + 1}/{self.max_retries}) in {delay:.1f}s..."
                            )
                            await asyncio.sleep(delay)
                        else:
                            completed += 1
                            logging.error(f"[{completed}/{total} done] Part {idx + 1} FAILED (rate limit): {label}")
                            return "Rate limit error - max retries reached"

                    except Exception as e:
                        page = await self._reset_or_replace_page(page)
                        if attempt < self.max_retries:
                            delay = (2 ** (attempt + 1)) + random.uniform(0.5, 1.5)
                            logging.warning(
                                f"[Part {idx + 1}/{total}] Error on {label}: {e}. "
                                f"Retrying ({attempt + 1}/{self.max_retries}) in {delay:.1f}s..."
                            )
                            await asyncio.sleep(delay)
                        else:
                            completed += 1
                            logging.error(f"[{completed}/{total} done] Part {idx + 1} FAILED: {label} -> {e}")
                            return f"Error: {e}"

                return "Failed after multiple attempts"
            finally:
                self._page_queue.put_nowait(page)

        # asyncio.gather guarantees the returned list preserves the exact order of `links`
        results = await asyncio.gather(*(_process_one(i, link) for i, link in enumerate(links)))
        return list(results)


async def _extract_download_link_playwright(url: str) -> str:
    """Extract download link using standalone Playwright instance with stealth."""
    async with async_playwright() as p:
        launch_args = ['--disable-blink-features=AutomationControlled', '--no-sandbox']
        try:
            browser = await p.chromium.launch(headless=True, channel="chrome", args=launch_args)
        except Exception:
            browser = await p.chromium.launch(headless=True, args=launch_args)

        context = await browser.new_context(user_agent=USER_AGENT, accept_downloads=True)
        page = await context.new_page()
        await Stealth().apply_stealth_async(page)

        try:
            return await extract_download_link_from_page(page, url)
        finally:
            await browser.close()


async def _extract_download_link(url: str) -> str:
    """Extract download link: tries fast HTML regex first, falls back to Playwright."""
    loop = asyncio.get_running_loop()
    html = await loop.run_in_executor(None, _fetch_page_html, url)
    if html:
        lower = html.lower()
        if any(kw in lower for kw in RATE_LIMIT_KEYWORDS):
            raise RateLimitedException("Rate limiting detected")
        match = DOWNLOAD_LINK_PATTERN.search(html)
        if match:
            return match.group(1)

    return await _extract_download_link_playwright(url)


def _get_semaphore() -> asyncio.Semaphore:
    global _SEMAPHORE
    if _SEMAPHORE is None:
        _SEMAPHORE = asyncio.Semaphore(DEFAULT_CONCURRENCY)
    return _SEMAPHORE


async def get_final_download_fuckingfast_async(url: str, max_retries: int = 3) -> str:
    """Get the final download link with retry mechanism for rate limiting (bounded concurrency)."""
    async with _get_semaphore():
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


async def process_fuckingfast_links_batch(
    links: list[str],
    concurrency: int = DEFAULT_CONCURRENCY,
    max_retries: int = 3,
) -> list[str]:
    """
    Concurrent batch processor that reuses a single stealth browser session
    across pooled tabs while preserving the exact order of `links`.
    """
    if not links:
        return []

    async with FuckingFastBatchExtractor(concurrency=concurrency, max_retries=max_retries) as extractor:
        return await extractor.process_links(links)
