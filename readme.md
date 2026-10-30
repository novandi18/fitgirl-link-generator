# FitGirl Link Generator (Updated Version)

A high-performance Python tool that extracts and processes FitGirl Repack links to obtain direct download URLs from FuckingFast host, ready for download managers like **Internet Download Manager (IDM)** and **JDownloader**.

## What's New in this Updated Version

* **Cloudflare Turnstile & Bot Management Support**: Bypasses Cloudflare checks using automated Playwright stealth profiles.
* **Modern HTMX & 2-Click Ad Handling**: Fully supports FuckingFast's updated HTMX architecture (`hx-post="/f/<id>/go"`), automatically closing ad popups on the first click and capturing the direct download stream and `HX-Redirect` header on the second click.
* **Session Reuse & Concurrent Tab Pool**: Reuses a single stealth browser context with configurable parallel tabs (`--concurrency`) to extract multiple part files asynchronously while strictly preserving part order.
* **Multiple URLs & Batch Text File Input**: Supports passing multiple FitGirl repack URLs via `--url` (or inside `--file`) as well as custom lists of FuckingFast URLs.

## Features

- Automatically extracts FuckingFast download links from one or multiple FitGirl repack pages or custom URL text files
- Async parallel extraction across pooled browser tabs while keeping part files strictly in order (`part1`, `part2`, ..., `partN`)
- Bypasses Cloudflare Turnstile, link shorteners, and ad popunders
- Generates direct, resumable download links compatible with IDM and JDownloader
- Organizes direct links in IDM-ready text files per game
- Works with single files, multi-part RAR archives, optional bonus files, and selective languages
- Smart rate-limiting detection and retry backoff

## Prerequisites

- Python 3.8+
- Playwright for Python
- BeautifulSoup4
- Requests
- Playwright-Stealth
- Google Chrome or Chromium

## Installation

1. Clone this repository:

```bash
git clone https://github.com/EditByDenzel/fitgirl-link-generator-updated.git
cd fitgirl-link-generator-updated
```

2. Install dependencies:

```bash
pip install playwright requests beautifulsoup4 playwright-stealth
```

3. Ensure Playwright browser is installed (or use your system Chrome):

```bash
playwright install chromium
```

## Usage

### 1. From One or More FitGirl Repack Page URLs
Run the script with one or multiple FitGirl repack URLs (separated by spaces or commas):

```bash
# Single URL
python app.py --url https://fitgirl-repacks.site/planet-zoo-2/

# Multiple URLs + custom async concurrency
python app.py --url https://fitgirl-repacks.site/planet-zoo-2/ https://fitgirl-repacks.site/elden-ring/ --concurrency 4
```

**Options:**
- `--url`, `-u` [Strings]: One or more FitGirl repack page URLs (space or comma separated).
- `--file`, `-f` [Paths]: Path(s) to text file(s) containing FitGirl repack URLs or FuckingFast links (one per line).
- `--concurrency`, `-c` [Int]: Number of parallel browser tabs for async link extraction (default: `3`).
- `--noBonus` [Flag]: Exclude bonus content links (`fg-optional*`).
- `--noLanguage` [Flag]: Exclude selective language packs (`fg-selective*`).

Example:
```bash
python app.py --url https://fitgirl-repacks.site/game-1/ https://fitgirl-repacks.site/game-2/ --noBonus --noLanguage -c 3
```

### 2. From a Text File of URLs
Your text file can contain multiple FitGirl repack page URLs, direct FuckingFast links, or both:

```bash
python app.py --file my_links.txt
```

Each game/target will have its direct download links saved in strict part order to `output/<name>_links.txt`.

## How to Import into IDM

1. Open **Internet Download Manager (IDM)**.
2. Go to **Tasks** -> **Import** -> **From text file**.
3. Select the generated text file in the `output/` directory.
4. Click **Check All** -> **OK** -> Start Queue.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
