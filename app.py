import argparse
import requests
from bs4 import BeautifulSoup
import re
import os
import time
from download_util import get_final_download_fuckingfast


def extract_links(url):
    """Extract FuckingFast download links from the webpage"""
    response = requests.get(url)
    if response.status_code != 200:
        print(f"Failed to retrieve the page: {response.status_code}")
        return []
    
    soup = BeautifulSoup(response.text, 'html.parser')
    links = []

    pattern = re.compile(r'https://fuckingfast\.co/\w+#.*?(?:\.part\d+\.rar|\.rar)')
    for a in soup.find_all('a', href=pattern):
        links.append(a['href'])

    return links


def main():
    parser = argparse.ArgumentParser(description='Generate download links from FitGirl repacks')
    parser.add_argument('--url', type=str, required=True,
                        help='FitGirl repack URL to extract download links from')
    args = parser.parse_args()
    
    url = args.url
    
    print(f"Fetching FuckingFast links from {url}")
    
    links = extract_links(url)
    
    if not links:
        print("No FuckingFast links found")
        return
    
    print(f"Found {len(links)} links. Processing...")
    
    final_links = []
    for i, link in enumerate(links):
        print(f"Processing link {i+1}/{len(links)}: {link}")
        try:
            final_link = get_final_download_fuckingfast(link)
            final_links.append(final_link)
            print(f"Final link: {final_link}")
            
            if i < len(links) - 1:
                time.sleep(2)
        except Exception as e:
            print(f"Error processing link: {e}")
    
    game_name = url.rstrip('/').split('/')[-1]
    
    output_dir = os.path.join(os.getcwd(), "output")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created output directory: {output_dir}")
    
    output_file = os.path.join(output_dir, f"{game_name}_fitgirl_links.txt")
    with open(output_file, 'w') as f:
        for link in final_links:
            f.write(f"{link}\n")
    
    print(f"Links saved to {output_file}")


if __name__ == "__main__":
    main()