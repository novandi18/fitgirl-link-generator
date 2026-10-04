import argparse
import requests
import asyncio
from bs4 import BeautifulSoup
import re
import os
import sys
from download_util import (
    get_final_download_fuckingfast_async,
    process_fuckingfast_links_batch,
)


def extract_links(url, exclude_bonus=False, exclude_language=False):
    """Extract FuckingFast download links from the FitGirl repack webpage"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"Failed to retrieve the page: {response.status_code}")
        return []
    
    soup = BeautifulSoup(response.text, 'html.parser')
    links = []

    pattern = re.compile(r'https://fuckingfast\.co/\w+#.*?(?:\.part\d+\.rar|\.rar|\.bin)')
    for a in soup.find_all('a', href=pattern):
        href = a['href']
        if exclude_bonus and 'fg-optional' in href and (href.endswith('.part1.rar') or href.endswith('.rar')):
            continue
        if exclude_language and 'fg-selective' in href and href.endswith('.bin'):
            continue
        links.append(href)

    return links


async def async_main():
    parser = argparse.ArgumentParser(description='Generate direct download links from FitGirl repacks & FuckingFast')
    parser.add_argument('--url', type=str,
                        help='FitGirl repack URL to extract download links from')
    parser.add_argument('--file', type=str,
                        help='Path to a text file containing FuckingFast links (one per line)')
    parser.add_argument('--noBonus', action='store_true',
                        help='Exclude bonus content links (files starting with "fg-optional")')
    parser.add_argument('--noLanguage', action='store_true',
                        help='Exclude selective language links (files starting with "fg-selective" and ending with ".bin")')
    args = parser.parse_args()
    
    if not args.url and not args.file:
        parser.error("Either --url or --file must be specified.")

    links = []
    output_prefix = "fitgirl"

    if args.url:
        print(f"Fetching repack page: {args.url}")
        links = extract_links(args.url, args.noBonus, args.noLanguage)
        output_prefix = args.url.rstrip('/').split('/')[-1]
    elif args.file:
        print(f"Reading links from file: {args.file}")
        with open(args.file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith("http"):
                    links.append(line)
        output_prefix = os.path.splitext(os.path.basename(args.file))[0]

    if not links:
        print("No FuckingFast links found to process.")
        return
    
    print(f"Processing {len(links)} links with browser automation...")
    
    try:
        final_links = await process_fuckingfast_links_batch(links)
        
        output_dir = os.path.join(os.getcwd(), "output")
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, f"{output_prefix}_links.txt")
        
        success_count = 0
        with open(output_file, 'w', encoding='utf-8') as f:
            for link in final_links:
                if link and not (link.startswith("Error:") or link == "Download link not found" or "Rate limit error" in link):
                    f.write(f"{link}\n")
                    success_count += 1
        
        print(f"\nCompleted: {success_count}/{len(links)} direct links extracted successfully.")
        print(f"Saved to: {output_file}")
        print("Ready for IDM import: Tasks -> Import -> From text file")
    
    except Exception as e:
        print(f"Error processing links: {e}")


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()