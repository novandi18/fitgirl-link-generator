# FitGirl Link Generator

A Python tool that extracts and processes FitGirl Repack links to obtain direct download URLs from FuckingFast host.

## Features

- Automatically extracts FuckingFast download links from FitGirl repack pages
- Bypasses link shorteners and countdown timers
- Generates direct download links that can be used with download managers like IDM
- Organizes download links in a text file for easy access
- Works with both single files and multi-part archives
- Options to exclude bonus content and language files
- Smart rate limiting detection with exponential backoff retry mechanism

## Prerequisites

- Python 3.7+
- Playwright for Python
- BeautifulSoup4
- Requests
- Playwright-Stealth

## Installation

1. Clone this repository:

```
git clone https://github.com/novandi18/fitgirl-link-generator.git
cd fitgirl-link-generator
```

2. Create a virtual environment (recommended):

```
python -m venv venv
source venv/bin/activate  # On Windows: call venv\Scripts\activate
```

3. Install dependencies:

```
pip install playwright requests beautifulsoup4 playwright-stealth
pip install --upgrade setuptools
```

4. Install Playwright browsers:

```
playwright install
```

## Usage

Run the script with the URL of a FitGirl repack page:

```
python app.py --url https://fitgirl-repacks.site/game-name/
```

### Command Line Options

- `--url` [Required]: The URL of the FitGirl repack page
- `--noBonus`: Exclude bonus content links (files starting with "fg-optional")
- `--noLanguage`: Exclude selective language links (files starting with "fg-selective" and ending with ".bin")

Example with options:

```
python app.py --url https://fitgirl-repacks.site/game-name/ --noBonus --noLanguage
```

The script will:

1. Extract all FuckingFast download links from the page
2. Process each link to obtain the direct download URL
3. Save all direct download links to `output/game-name_fitgirl_links.txt`

## How It Works

The tool works in multiple steps:

1. Link Extraction

The script visits the specified FitGirl repack page and finds all download links for the FuckingFast host using BeautifulSoup and regex pattern matching. It can optionally filter out bonus content and language files.

2. Link Processing

For each extracted link, the script:

- Opens the FuckingFast page using Playwright
- Uses stealth techniques to avoid bot detection
- Extracts the direct download URL from the page's JavaScript code
- Handles rate limiting with automatic retries and exponential backoff
- Compiles all processed links into a single text file

## Rate Limiting Handling

The tool implements smart rate limit detection and will automatically:

- Detect when FuckingFast imposes rate limits
- Implement exponential backoff with random jitter between retries
- Make multiple attempts before giving up
- Provide clear feedback when rate limiting occurs

## Example Output

After running the script, you'll find a file in the output directory with all direct download links:

```
https://fuckingfast.co/dl/PB4Xksv-tBWYX23MRlqpIFsZDBZHlOQ8cFpEjEO16ENovo0TZrlS9-kqRJm9EYmMx-Oqo3Q78ZMNl3fWmXt5uI1mK-C41UJLXuAew5DH8FDgPo6tXye8oaGDM0oD1jpoVMA6qq-uoiO2o69dtN_xB-IY4z1zwe1SRD4
https://fuckingfast.co/dl/QEqdlUmgud7OfiO5l7rbzFZPDBZHlOQ8cFpEjEO16ENTvpYfZr9Q9OwqRZm9EYmVxuKqo3U78ZQNl3PWFC
...
```

These links can be directly imported into download managers like Internet Download Manager (IDM) or JDownloader.

## Advanced Configuration

You can modify the `download_util.py` file to change browser behavior:

- Change `headless=True` to `headless=False` to see the browser in action
- Adjust the `max_retries` parameter (default: 3) for more retry attempts during rate limiting
- Modify the browser window size (currently randomized between 1280x800 and 1920x1080)
- Change the user agent string if needed
- Modify timeout values (currently set to 60000ms) if you have a slower internet connection

## Localization Note

The success message displayed after completion ("Download selesai") is in Indonesian. This means "Download completed".

## Troubleshooting

If you encounter issues:

1. **No links found**: Ensure the URL is correct and contains FuckingFast download links
2. **Download link not found**: The script might be failing to parse the page - try running with `headless=False` to see what's happening
3. **Rate limit errors**: If you're seeing rate limit messages, wait a while before trying again or try with fewer links at a time

## Disclaimer

This tool is for educational purposes only. Please respect copyright laws and support game developers by purchasing games you enjoy. FitGirl repacks should only be used to try games before purchasing or to download games you already own.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
