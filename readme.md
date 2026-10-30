# FitGirl Link Generator (Updated Version)

A high-performance Python tool that extracts and processes FitGirl Repack links to obtain direct download URLs from FuckingFast host, ready for download managers like **Internet Download Manager (IDM)** and **JDownloader**.

## What's New in this Updated Version

* **Cloudflare Turnstile & Bot Management Support**: Bypasses Cloudflare checks using automated Playwright stealth profiles.
* **Modern HTMX & 2-Click Ad Handling**: Fully supports FuckingFast's updated HTMX architecture (`hx-post="/f/<id>/go"`), automatically closing ad popups on the first click and capturing the direct download stream and `HX-Redirect` header on the second click.
* **Session Reuse & Concurrent Tab Pool**: Reuses a single stealth browser context with configurable parallel tabs (`--concurrency`) to extract multiple part files asynchronously while strictly preserving part order.
* **Multiple URLs & Batch Text File Input**: Supports passing multiple FitGirl repack URLs via `--url` (or inside `--file`) as well as custom lists of FuckingFast URLs.
* **Interactive CLI Game Search (`--search`)**: Search FitGirl Repacks directly from the terminal and pick one or more games to extract without opening a browser.
* **Specific Language Filtering (`--lang`)**: Keep only the language packs you need (e.g. `--lang english` or `--lang english,japanese`) and skip all other `fg-selective-*` packs.
* **Checkpoint / Resume & Auto-Save Failed Links (`--resume`)**: Saves progress incrementally to `output/.cache/` as each part resolves, allowing instant resume for large multi-part games and automatically exporting any failed links to `output/<game>_failed.txt`.
* **Game Updates / Patch Extraction (`--updates`)**: Extracts FuckingFast patch/update links from the *"Game Updates"* section into a separate `output/<game>_updates.txt` file in chronological order.

## Features

- Automatically extracts FuckingFast download links from one or multiple FitGirl repack pages, CLI search queries, or custom URL text files
- Async parallel extraction across pooled browser tabs while keeping part files strictly in order (`part1`, `part2`, ..., `partN`)
- Specific selective language filtering (`--lang`) and optional bonus filtering (`--noBonus`)
- Incremental checkpoint caching (`--resume`) and automatic failed-links export (`*_failed.txt`)
- Separate extraction for Game Updates / Patches (`--updates` / `--updatesOnly`)
- Bypasses Cloudflare Turnstile, link shorteners, and ad popunders
- Generates direct, resumable download links compatible with IDM and JDownloader

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
# Single URL with only English language pack
python app.py --url https://fitgirl-repacks.site/planet-zoo-2/ --lang english

# Multiple URLs + custom async concurrency + game updates
python app.py --url https://fitgirl-repacks.site/planet-zoo-2/ https://fitgirl-repacks.site/elden-ring/ -c 4 --updates

# Resume an interrupted or partially failed extraction
python app.py --url https://fitgirl-repacks.site/planet-zoo-2/ --resume
```

### 2. Interactive CLI Game Search (`--search`)
Search for games directly from the terminal and choose which results to extract:

```bash
python app.py --search "planet zoo" --lang english --noBonus
```

### 3. From a Text File of URLs (`--file`)
Your text file can contain multiple FitGirl repack page URLs, direct FuckingFast links (including a previously generated `*_failed.txt` file), or both:

```bash
python app.py --file my_links.txt
```

### CLI Options Reference
- `--url`, `-u` [Strings]: One or more FitGirl repack page URLs (space or comma separated).
- `--file`, `-f` [Paths]: Path(s) to text file(s) containing FitGirl repack URLs or FuckingFast links (one per line).
- `--search`, `-s` [Query]: Search FitGirl Repacks interactively from the terminal.
- `--concurrency`, `-c` [Int]: Number of parallel browser tabs for async link extraction (default: `3`).
- `--lang`, `-l` [Languages]: Keep only specific selective language(s) (e.g. `--lang english` or `--lang english,japanese`).
- `--resume`, `-r` [Flag]: Resume from saved checkpoint in `output/.cache/` and only process unresolved parts.
- `--updates`, `-U` [Flag]: Also extract Game Update / Patch links into `output/<game>_updates.txt`.
- `--updatesOnly` [Flag]: Extract ONLY Game Update / Patch links into `output/<game>_updates.txt`.
- `--noBonus` [Flag]: Exclude bonus content links (`fg-optional*`).
- `--noLanguage` [Flag]: Exclude all selective language packs (`fg-selective*`).

## How to Import into IDM

1. Open **Internet Download Manager (IDM)**.
2. Go to **Tasks** -> **Import** -> **From text file**.
3. Select the generated text file in the `output/` directory.
4. Click **Check All** -> **OK** -> Start Queue.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
