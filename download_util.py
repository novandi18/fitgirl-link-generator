from playwright.async_api import async_playwright
from playwright_stealth import stealth_async
import asyncio
import random
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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


async def _extract_download_link(url: str) -> str:
    """Internal function to extract download link with improved stealth"""
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
        
        await stealth_async(page)
        
        await asyncio.sleep(random.uniform(0.5, 1.5))
        
        try:
            # Navigate with extended timeout
            await page.goto(url, wait_until='networkidle', timeout=60000)
            
            # Check for rate limiting
            rate_limited = await page.evaluate("""() => {
                return document.body.textContent.includes('rate limited') || 
                    document.body.textContent.includes('Rate Limit') ||
                    document.body.textContent.includes('Too many requests');
            }""")
            
            if rate_limited:
                await browser.close()
                raise RateLimitedException("Rate limiting detected")
            
            # Add slight delay to let any scripts initialize
            await asyncio.sleep(random.uniform(1, 2))
            
            download_link = await page.evaluate("""() => {
                const scripts = document.querySelectorAll('script');
                let dlLink = null;
                
                for (const script of scripts) {
                    const content = script.textContent || script.innerText;
                    if (!content) continue;
                    
                    if (content.includes('function download()')) {
                        // Try multiple regex patterns
                        let match = content.match(/window\\.open\\("(https:\\/\\/fuckingfast\\.co\\/dl\\/[^"]+)"/);
                        if (!match) {
                            match = content.match(/window\.open\("(https:\/\/fuckingfast\.co\/dl\/[^"]+)"/);
                        }
                        if (match && match[1]) {
                            dlLink = match[1];
                            break;
                        }
                    }
                }

                // Fallback: look for download button or direct link
                if (!dlLink) {
                    const downloadBtns = [...document.querySelectorAll('a[href*="fuckingfast.co/dl/"]')];
                    if (downloadBtns.length > 0) {
                        dlLink = downloadBtns[0].href;
                    }
                }

                return dlLink;
            }""")
            
            await browser.close()
            
            if not download_link:
                return "Download link not found"
                
            return download_link
            
        except RateLimitedException:
            await browser.close()
            raise
            
        except Exception as e:
            await browser.close()
            raise