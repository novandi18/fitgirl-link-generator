import argparse
import requests
import asyncio
from bs4 import BeautifulSoup
import re
import os
import time
from download_util import get_final_download_fuckingfast_async


def extract_links(url, exclude_bonus=False, exclude_language=False):
    """Extract FuckingFast download links from the webpage"""
    response = requests.get(url)
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


async def process_links_async(links):
    tasks = [get_final_download_fuckingfast_async(link) for link in links]
    return await asyncio.gather(*tasks)


async def async_main():
    parser = argparse.ArgumentParser(description='Generate download links from FitGirl repacks')
    parser.add_argument('--url', type=str, required=True,
                        help='FitGirl repack URL to extract download links from')
    parser.add_argument('--noBonus', action='store_true',
                        help='Exclude bonus content links (files starting with "fg-optional")')
    parser.add_argument('--noLanguage', action='store_true',
                        help='Exclude selective language links (files starting with "fg-selective" and ending with ".bin")')
    args = parser.parse_args()
    
    url = args.url
    exclude_bonus = args.noBonus
    exclude_language = args.noLanguage
    
    links = extract_links(url, exclude_bonus, exclude_language)
    
    if not links:
        print("No FuckingFast links found")
        return
    
    print(f"Downloading {len(links)} files...")
    
    try:
        final_links = await process_links_async(links)
        
        rate_limited_links = [link for link in final_links if "Rate limit error" in link]
        if rate_limited_links:
            print("Process cancelled due to rate limiting. Please try again later.")
            return
        
        error_links = [link for link in final_links if link.startswith("Error:") or link == "Download link not found"]
        if error_links:
            print(f"Warning: {len(error_links)} links could not be processed.")
        
        game_name = url.rstrip('/').split('/')[-1]
        
        output_dir = os.path.join(os.getcwd(), "output")
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        output_file = os.path.join(output_dir, f"{game_name}_fitgirl_links.txt")
        with open(output_file, 'w') as f:
            for link in final_links:
                if not (link.startswith("Error:") or link == "Download link not found" or "Rate limit error" in link):
                    f.write(f"{link}\n")
        
        print(f"Download selesai, {output_file}")
    
    except Exception as e:
        print(f"Error processing links: {e}")


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()