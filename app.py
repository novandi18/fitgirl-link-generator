import argparse
import asyncio
import os
import re
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
from download_util import (
    DEFAULT_CONCURRENCY,
    FuckingFastBatchExtractor,
    get_final_download_fuckingfast_async,
    is_valid_direct_link,
    process_fuckingfast_links_batch,
    sort_fuckingfast_links,
)


def _sanitize_filename(name: str) -> str:
    """Sanitize a string to be safe as a Windows/POSIX filename prefix."""
    cleaned = re.sub(r'[<>:"/\\|?*]+', '_', name).strip(' ._')
    return cleaned or "fitgirl"


def _slug_from_url(url: str) -> str:
    """Extract clean game slug from a FitGirl repack URL."""
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split('/') if p]
    slug = parts[-1] if parts else parsed.netloc
    return _sanitize_filename(slug)


def _is_fuckingfast_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return "fuckingfast.co" in host


def extract_links(url: str, exclude_bonus: bool = False, exclude_language: bool = False) -> list[str]:
    """Extract and sort FuckingFast download links from a FitGirl repack webpage."""
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ),
    }
    try:
        response = requests.get(url, headers=headers, timeout=20)
    except requests.RequestException as e:
        print(f"Failed to retrieve {url}: {e}")
        return []

    if response.status_code != 200:
        print(f"Failed to retrieve {url}: HTTP {response.status_code}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    links: list[str] = []

    pattern = re.compile(
        r'https://fuckingfast\.co/[\w-]+#[^\s"\'<>]*?(?:\.part\d+\.rar|\.rar|\.bin)',
        re.IGNORECASE,
    )
    for a in soup.find_all('a', href=pattern):
        href = a['href']
        lower_href = href.lower()
        if exclude_bonus and 'fg-optional' in lower_href:
            continue
        if exclude_language and 'fg-selective' in lower_href:
            continue
        links.append(href)

    return sort_fuckingfast_links(links)


def _parse_url_inputs(raw_urls: list[str] | None) -> list[str]:
    """Support space-separated and comma-separated URLs from --url."""
    if not raw_urls:
        return []
    parsed_urls: list[str] = []
    for item in raw_urls:
        for part in item.split(','):
            u = part.strip()
            if u.startswith("http"):
                parsed_urls.append(u)
    return parsed_urls


async def async_main():
    parser = argparse.ArgumentParser(
        description='Generate direct download links from FitGirl repacks & FuckingFast (Async & Multi-URL)'
    )
    parser.add_argument(
        '--url', '-u',
        nargs='+',
        action='extend',
        type=str,
        help='One or more FitGirl repack URLs (space or comma separated)',
    )
    parser.add_argument(
        '--file', '-f',
        nargs='+',
        action='extend',
        type=str,
        help='Path(s) to text file(s) containing FitGirl repack URLs or FuckingFast links (one per line)',
    )
    parser.add_argument(
        '--concurrency', '-c',
        type=int,
        default=DEFAULT_CONCURRENCY,
        help=f'Number of parallel browser tabs for async link extraction (default: {DEFAULT_CONCURRENCY})',
    )
    parser.add_argument(
        '--noBonus',
        action='store_true',
        help='Exclude bonus content links (files containing "fg-optional")',
    )
    parser.add_argument(
        '--noLanguage',
        action='store_true',
        help='Exclude selective language links (files containing "fg-selective")',
    )
    args = parser.parse_args()

    if not args.url and not args.file:
        parser.error("Either --url or --file must be specified.")

    if args.concurrency < 1:
        parser.error("--concurrency must be at least 1.")

    fitgirl_urls: list[str] = []
    seen_fitgirl_urls: set[str] = set()
    direct_batches: list[tuple[str, str, list[str]]] = []

    def _add_fitgirl_url(u: str):
        normalized = u.rstrip('/')
        if normalized not in seen_fitgirl_urls:
            seen_fitgirl_urls.add(normalized)
            fitgirl_urls.append(u)

    # 1. Collect URLs from --url
    cli_urls = _parse_url_inputs(args.url)
    cli_direct_links: list[str] = []
    for u in cli_urls:
        if _is_fuckingfast_url(u):
            cli_direct_links.append(u)
        else:
            _add_fitgirl_url(u)

    if cli_direct_links:
        direct_batches.append(("fitgirl", "CLI direct links", sort_fuckingfast_links(cli_direct_links)))

    # 2. Collect URLs from --file
    if args.file:
        for filepath in args.file:
            if not os.path.isfile(filepath):
                print(f"File not found, skipping: {filepath}")
                continue
            print(f"Reading links from file: {filepath}")
            file_ff_links: list[str] = []
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if line.startswith("http"):
                        if _is_fuckingfast_url(line):
                            file_ff_links.append(line)
                        else:
                            _add_fitgirl_url(line)

            if file_ff_links:
                prefix = _sanitize_filename(os.path.splitext(os.path.basename(filepath))[0])
                direct_batches.append((prefix, f"File: {filepath}", sort_fuckingfast_links(file_ff_links)))

    # 3. Scrape FitGirl repack pages concurrently (preserving URL order)
    jobs: list[tuple[str, str, list[str]]] = []
    if fitgirl_urls:
        print(f"Fetching {len(fitgirl_urls)} FitGirl repack page(s)...")
        scraped_lists = await asyncio.gather(
            *(asyncio.to_thread(extract_links, u, args.noBonus, args.noLanguage) for u in fitgirl_urls)
        )
        for u, extracted in zip(fitgirl_urls, scraped_lists):
            if extracted:
                jobs.append((_slug_from_url(u), u, extracted))
            else:
                print(f"No FuckingFast links found on: {u}")

    jobs.extend(direct_batches)

    if not jobs:
        print("No FuckingFast links found to process.")
        return

    output_dir = os.path.join(os.getcwd(), "output")
    os.makedirs(output_dir, exist_ok=True)
    used_filenames: set[str] = set()

    def _allocate_output_path(prefix: str) -> str:
        candidate = f"{prefix}_links.txt"
        counter = 2
        while candidate.lower() in used_filenames:
            candidate = f"{prefix}_{counter}_links.txt"
            counter += 1
        used_filenames.add(candidate.lower())
        return os.path.join(output_dir, candidate)

    total_jobs = len(jobs)
    summary_rows: list[tuple[str, int, int, str]] = []

    print(
        f"\nStarting async browser extraction across {total_jobs} target(s) "
        f"(concurrency={args.concurrency})..."
    )

    try:
        async with FuckingFastBatchExtractor(concurrency=args.concurrency) as extractor:
            for job_idx, (prefix, source_desc, links) in enumerate(jobs, 1):
                print(f"\n[{job_idx}/{total_jobs}] Target: {source_desc}")
                print(f"Extracting {len(links)} ordered part/file link(s)...")

                final_links = await extractor.process_links(links)
                output_file = _allocate_output_path(prefix)

                success_count = 0
                failed_parts: list[tuple[int, str, str]] = []

                with open(output_file, 'w', encoding='utf-8') as f:
                    for part_num, (src_link, direct_link) in enumerate(zip(links, final_links), 1):
                        if is_valid_direct_link(direct_link):
                            f.write(f"{direct_link}\n")
                            success_count += 1
                        else:
                            failed_parts.append((part_num, src_link, str(direct_link)))

                print(f"Completed [{job_idx}/{total_jobs}]: {success_count}/{len(links)} direct links saved.")
                print(f"Saved to: {output_file}")

                if failed_parts:
                    print("Warning - the following part(s) failed to resolve:")
                    for part_num, src_link, reason in failed_parts:
                        print(f"  - Part #{part_num}: {src_link} ({reason})")

                summary_rows.append((source_desc, success_count, len(links), output_file))

        if total_jobs > 1:
            print("\n=== Batch Summary ===")
            for source_desc, ok_cnt, total_cnt, out_path in summary_rows:
                print(f"- {source_desc}: {ok_cnt}/{total_cnt} -> {out_path}")

        print("\nReady for IDM import: Tasks -> Import -> From text file")

    except Exception as e:
        print(f"Error processing links: {e}")


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
