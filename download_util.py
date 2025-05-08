from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync


def get_final_download_fuckingfast(url: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        stealth_sync(page)

        page.goto(url, wait_until='networkidle')
        
        download_link = page.evaluate("""() => {
            const scripts = document.querySelectorAll('script');
            let dlLink = null;
            
            for (const script of scripts) {
                const content = script.textContent || script.innerText;
                if (content && content.includes('function download()')) {
                    // Extract the URL with a regex pattern that matches the window.open call with the download URL
                    const match = content.match(/window\\.open\\("(https:\\/\\/fuckingfast\\.co\\/dl\\/[^"]+)"/);
                    if (match && match[1]) {
                        dlLink = match[1];
                        break;
                    }
                }
            }

            return dlLink;
        }""")
        
        browser.close()
        
        if not download_link:
            return "Download link not found"
            
        return download_link
