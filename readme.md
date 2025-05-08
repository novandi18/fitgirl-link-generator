# FitGirl Link Generator

A Python tool that extracts and processes FitGirl Repack links to obtain direct download URLs from FuckingFast host.

## Features

- Automatically extracts FuckingFast download links from FitGirl repack pages
- Bypasses link shorteners and countdown timers
- Generates direct download links that can be used with download managers like IDM
- Organizes download links in a text file for easy access
- Works with both single files and multi-part archives

## Prerequisites

- Python 3.7+
- Playwright for Python
- BeautifulSoup4
- Requests

## Installation

1. Clone this repository:

```
git clone https://github.com/yourusername/fitgirl-link-generator.git
cd fitgirl-link-generator
```

2. Create a virtual environment (recommended):

```
python -m venv venv
source venv/bin/activate
```

3. Install dependencies:

```
pip install playwright requests beautifulsoup4 playwright-stealth
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

The script will:

1. Extract all FuckingFast download links from the page
2. Process each link to obtain the direct download URL
3. Save all direct download links to `output/game-name_fitgirl_links.txt`

## How It Works

The tool works in two main steps:

1. Link Extraction

The script visits the specified FitGirl repack page and finds all download links for the FuckingFast host using BeautifulSoup and regex pattern matching.

2. Link Processing

For each extracted link, the script:

- Opens the FuckingFast page using Playwright
- Uses stealth techniques to avoid bot detection
- Extracts the direct download URL from the page's JavaScript code
- Compiles all processed links into a single text file

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

- Change `headless=True` to `headless=False` if you want to see the browser in action
  Adjust timeout values if you have a slower internet connection
  Modify the user agent if needed
- Adjust timeout values if you have a slower internet connection
- Modify the user agent if needed

## Troubleshooting

If you encounter issues:

1. **No links found**: Ensure the URL is correct and contains FuckingFast download links
2. **Download link not found**: The script might be failing to parse the page - try running with `headless=False` to see what's happening

## Disclaimer

This tool is for educational purposes only. Please respect copyright laws and support game developers by purchasing games you enjoy. FitGirl repacks should only be used to try games before purchasing or to download games you already own.

## Licence

This project is licensed under the MIT License - see the LICENSE file for details.
