# FitGirl Link Generator (Updated Version)

A high-performance Python tool that extracts and processes FitGirl Repack links to obtain direct download URLs from FuckingFast host, ready for download managers like **Internet Download Manager (IDM)** and **JDownloader**.

## What's New in this Updated Version

* **Cloudflare Turnstile & Bot Management Support**: Bypasses Cloudflare checks using automated Playwright stealth profiles.
* **Modern HTMX & 2-Click Ad Handling**: Fully supports FuckingFast's updated HTMX architecture (`hx-post="/f/<id>/go"`), automatically closing ad popups on the first click and capturing the direct download stream and `HX-Redirect` header on the second click.
* **Session Reuse Batch Processing**: Reuses a single browser session context across all files to eliminate redundant Cloudflare verifications and prevent IP rate-limiting.
* **Batch Text File Input**: Added support for `--file` flag to process custom lists of FuckingFast URLs directly.

## Features

- Automatically extracts FuckingFast download links from FitGirl repack pages or custom URL text files
- Bypasses Cloudflare Turnstile, link shorteners, and ad popunders
- Generates direct, resumable download links compatible with IDM and JDownloader
- Organizes direct links in an IDM-ready text file
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

### 1. From a FitGirl Repack Page URL
Run the script with the URL of any FitGirl repack:

```bash
python app.py --url https://fitgirl-repacks.site/game-name/
```

**Options:**
- `--url` [String]: The URL of the FitGirl repack page.
- `--noBonus` [Flag]: Exclude bonus content links (`fg-optional*`).
- `--noLanguage` [Flag]: Exclude selective language packs (`fg-selective*`).

Example:
```bash
python app.py --url https://fitgirl-repacks.site/game-name/ --noBonus --noLanguage
```

### 2. From a Text File of URLs
If you already have a list of FuckingFast links:

```bash
python app.py --file my_links.txt
```

The script will resolve all direct download links and save them to `output/<name>_links.txt`.

## How to Import into IDM

1. Open **Internet Download Manager (IDM)**.
2. Go to **Tasks** $\rightarrow$ **Import** $\rightarrow$ **From text file**.
3. Select the generated text file in the `output/` directory.
4. Click **Check All** $\rightarrow$ **OK** $\rightarrow$ Start Queue.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
