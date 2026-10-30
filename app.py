import argparse
import asyncio
import json
import os
import re
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlparse
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

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    ),
}

NON_GAME_SLUGS = {
    'donations',
    'faq',
    'repacks-troubleshooting',
    'contacts',
    'all-my-repacks-a-z',
    'popular-repacks',
    ' popular-repacks-of-the-year',
}

NON_GAME_TITLE_PREFIXES = (
    'upcoming repacks',
    'updates digest',
    'monthly digest',
    'donations',
    'repacks troubleshooting',
    'faq',
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


def _parse_lang_inputs(raw_langs: list[str] | None) -> list[str]:
    """Normalize space-separated or comma-separated language filters into lowercase tokens."""
    if not raw_langs:
        return []
    langs: list[str] = []
    for item in raw_langs:
        for part in item.split(','):
            cleaned = part.strip().lower()
            if cleaned and cleaned not in langs:
                langs.append(cleaned)
    return langs


def _matches_language_filter(
    href: str,
    exclude_language: bool = False,
    allowed_langs: list[str] | None = None,
) -> bool:
    """
    Determine whether a link should be kept based on language filters.
    - Non-selective files always return True.
    - If `allowed_langs` is provided, only selective files matching at least one
      requested language after `fg-selective-` are kept.
    - Otherwise, if `exclude_language` is True, all `fg-selective` files are excluded.
    """
    lower_href = href.lower()
    if 'fg-selective' not in lower_href:
        return True

    if allowed_langs:
        after_selective = lower_href.split('fg-selective-', 1)[-1]
        # Strip file extensions (.part1.rar, .rar, .bin, etc.) to inspect language tokens
        lang_segment = re.sub(r'(?:\.part\d+)?\.(?:rar|bin|7z|zip)$', '', after_selective)
        lang_tokens = [t for t in re.split(r'[^a-z0-9]+', lang_segment) if t]
        for req_lang in allowed_langs:
            req_norm = req_lang.strip().lower()
            if req_norm in lang_tokens or req_norm in lang_segment:
                return True
        return False

    if exclude_language:
        return False

    return True


def filter_fitgirl_links(
    links: list[str],
    exclude_bonus: bool = False,
    exclude_language: bool = False,
    allowed_langs: list[str] | None = None,
) -> list[str]:
    """Filter a list of FuckingFast links by bonus and language preferences."""
    filtered: list[str] = []
    for href in links:
        lower_href = href.lower()
        if exclude_bonus and 'fg-optional' in lower_href:
            continue
        if not _matches_language_filter(href, exclude_language=exclude_language, allowed_langs=allowed_langs):
            continue
        filtered.append(href)
    return filtered


def _is_in_updates_section(a_tag) -> bool:
    """Return True if an <a> tag belongs to the 'Game Updates' section on a FitGirl page."""
    # 1. Check ancestor Shortcodes-Ultimate spoiler title
    spoiler = a_tag.find_parent(class_=re.compile(r'\bsu-spoiler\b'))
    if spoiler:
        title_el = spoiler.find(class_=re.compile(r'\bsu-spoiler-title\b'))
        if title_el:
            title_text = title_el.get_text(" ", strip=True).lower()
            if any(k in title_text for k in ('game update', 'updates', 'patch', 'hotfix')):
                if 'download mirrors' not in title_text:
                    return True

    # 2. Check nearest preceding heading or strong section header
    for prev in a_tag.find_all_previous(['h1', 'h2', 'h3', 'h4', 'h5', 'p']):
        text = prev.get_text(" ", strip=True).lower()
        if not text:
            continue
        if prev.name in ('h1', 'h2', 'h3', 'h4', 'h5'):
            if 'game update' in text or 'updates – direct' in text or 'updates - direct' in text:
                return True
            if 'download mirrors' in text:
                break
        elif prev.name == 'p':
            strong = prev.find(['b', 'strong'])
            if strong:
                s_text = strong.get_text(" ", strip=True).lower()
                if 'game update' in s_text or 'updates – direct' in s_text or 'updates - direct' in s_text:
                    return True

    # 3. Heuristic fallback: link does not have FitGirl main repack markers and sits in an Update <li>
    href = a_tag.get('href', '')
    lower_href = href.lower()
    is_main_repack_marker = (
        'fitgirl-repacks.site' in lower_href
        or 'fg-optional' in lower_href
        or 'fg-selective' in lower_href
    )
    if not is_main_repack_marker:
        li = a_tag.find_parent('li')
        if li:
            li_text = li.get_text(" ", strip=True).lower()
            if any(k in li_text for k in ('update v', 'patch v', 'hotfix', 'elamigos', 'tenoke', 'rune')):
                return True
        if '#' in lower_href:
            frag = lower_href.split('#', 1)[1]
            if any(k in frag for k in ('update', 'patch', 'hotfix')):
                return True

    return False


def _enrich_update_href(a_tag, href: str, index: int) -> str:
    """Attach a readable #label fragment to an update link if it lacks one."""
    if '#' in href and href.split('#', 1)[1].strip():
        return href

    label = ""
    li = a_tag.find_parent('li')
    if li:
        bold = li.find(['b', 'strong'])
        if bold:
            label = bold.get_text(" ", strip=True)
    if not label:
        a_text = a_tag.get_text(" ", strip=True)
        if a_text and a_text.lower() not in ('fuckingfast', 'download', 'mirror', 'link'):
            label = a_text
    if not label:
        label = f"update_{index}"

    safe_label = re.sub(r'[^\w.\-]+', '_', label).strip('_')
    return f"{href}#{safe_label}" if safe_label else href


def extract_links_from_soup(
    soup: BeautifulSoup,
    exclude_bonus: bool = False,
    exclude_language: bool = False,
    allowed_langs: list[str] | None = None,
) -> list[str]:
    """Extract and sort main repack FuckingFast links from parsed FitGirl HTML."""
    pattern = re.compile(
        r'https://fuckingfast\.co/[\w-]+#[^\s"\'<>]*?(?:\.part\d+\.rar|\.rar|\.bin)',
        re.IGNORECASE,
    )
    raw_links: list[str] = []
    for a in soup.find_all('a', href=pattern):
        if _is_in_updates_section(a):
            continue
        raw_links.append(a['href'])

    filtered = filter_fitgirl_links(
        raw_links,
        exclude_bonus=exclude_bonus,
        exclude_language=exclude_language,
        allowed_langs=allowed_langs,
    )
    return sort_fuckingfast_links(filtered)


def extract_update_links_from_soup(soup: BeautifulSoup) -> list[str]:
    """Extract and sort Game Update / Patch FuckingFast links from parsed FitGirl HTML."""
    pattern = re.compile(r'https://fuckingfast\.co/[\w-]+(?:#[^\s"\'<>]*)?', re.IGNORECASE)
    update_links: list[str] = []
    for idx, a in enumerate(soup.find_all('a', href=pattern), 1):
        if _is_in_updates_section(a):
            enriched = _enrich_update_href(a, a['href'], idx)
            update_links.append(enriched)

    return sort_fuckingfast_links(update_links)


def scrape_fitgirl_page(
    url: str,
    exclude_bonus: bool = False,
    exclude_language: bool = False,
    allowed_langs: list[str] | None = None,
) -> tuple[list[str], list[str]]:
    """Fetch a FitGirl repack page once and return (main_links, update_links)."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=20)
    except requests.RequestException as e:
        print(f"Failed to retrieve {url}: {e}")
        return [], []

    if response.status_code != 200:
        print(f"Failed to retrieve {url}: HTTP {response.status_code}")
        return [], []

    soup = BeautifulSoup(response.text, 'html.parser')
    main_links = extract_links_from_soup(
        soup,
        exclude_bonus=exclude_bonus,
        exclude_language=exclude_language,
        allowed_langs=allowed_langs,
    )
    update_links = extract_update_links_from_soup(soup)
    return main_links, update_links


def extract_links(
    url: str,
    exclude_bonus: bool = False,
    exclude_language: bool = False,
    allowed_langs: list[str] | None = None,
) -> list[str]:
    """Extract and sort main FuckingFast download links from a FitGirl repack webpage."""
    main_links, _ = scrape_fitgirl_page(
        url,
        exclude_bonus=exclude_bonus,
        exclude_language=exclude_language,
        allowed_langs=allowed_langs,
    )
    return main_links


def extract_update_links(url: str) -> list[str]:
    """Extract and sort Game Update FuckingFast links from a FitGirl repack webpage."""
    _, update_links = scrape_fitgirl_page(url)
    return update_links


def search_fitgirl_games(query: str) -> list[dict[str, str]]:
    """Search FitGirl Repacks for `query` and return a list of {'title', 'url', 'date'} dicts."""
    search_url = f"https://fitgirl-repacks.site/?s={quote_plus(query.strip())}"
    try:
        response = requests.get(search_url, headers=HEADERS, timeout=20)
    except requests.RequestException as e:
        print(f"Search request failed: {e}")
        return []

    if response.status_code != 200:
        print(f"Search failed with HTTP {response.status_code}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    results: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    def _try_add(title: str, href: str, date_str: str = ""):
        if not title or not href.startswith("http"):
            return
        parsed = urlparse(href)
        if "fitgirl-repacks.site" not in parsed.netloc.lower():
            return
        path_parts = [p for p in parsed.path.split('/') if p]
        if len(path_parts) != 1:
            return
        slug = path_parts[0].lower()
        if slug in NON_GAME_SLUGS:
            return
        lower_title = title.lower().strip()
        if any(lower_title.startswith(prefix) for prefix in NON_GAME_TITLE_PREFIXES):
            return
        norm_url = href.rstrip('/') + '/'
        if norm_url not in seen_urls:
            seen_urls.add(norm_url)
            results.append({
                'title': title.strip(),
                'url': norm_url,
                'date': date_str.strip(),
            })

    for article in soup.find_all('article'):
        heading = article.find(['h1', 'h2', 'h3'], class_=re.compile(r'entry-title'))
        if not heading:
            continue
        a_tag = heading.find('a', href=True)
        if not a_tag:
            continue
        date_str = ""
        time_el = article.find('time', class_=re.compile(r'entry-date'))
        if time_el:
            date_str = time_el.get_text(" ", strip=True)
        _try_add(a_tag.get_text(" ", strip=True), a_tag['href'], date_str)

    if not results:
        for heading in soup.find_all(['h1', 'h2', 'h3'], class_=re.compile(r'entry-title')):
            a_tag = heading.find('a', href=True)
            if a_tag:
                _try_add(a_tag.get_text(" ", strip=True), a_tag['href'])

    return results


def parse_search_selection(selection: str, total: int) -> list[int] | None:
    """
    Parse interactive user selection string into 0-based indices.
    Returns:
      - `[]` if user chose to cancel ('q', 'quit', '0', '')
      - `list[int]` of valid 0-based indices
      - `None` if input was malformed or out of range
    """
    raw = selection.strip().lower()
    if not raw or raw in ('q', 'quit', 'exit', '0'):
        return []
    if raw in ('all', 'a', '*'):
        return list(range(total))

    chosen: list[int] = []
    tokens = [t.strip() for t in re.split(r'[,\s]+', raw) if t.strip()]
    if not tokens:
        return []

    for tok in tokens:
        if '-' in tok:
            bounds = tok.split('-', 1)
            if len(bounds) != 2 or not (bounds[0].isdigit() and bounds[1].isdigit()):
                return None
            start, end = int(bounds[0]), int(bounds[1])
            if start > end or start < 1 or end > total:
                return None
            for num in range(start, end + 1):
                if (num - 1) not in chosen:
                    chosen.append(num - 1)
        elif tok.isdigit():
            num = int(tok)
            if num < 1 or num > total:
                return None
            if (num - 1) not in chosen:
                chosen.append(num - 1)
        else:
            return None

    return chosen


def interactive_search_flow(query: str) -> list[str]:
    """Run interactive CLI search and return selected FitGirl repack URLs."""
    print(f"Searching FitGirl Repacks for: \"{query}\"...")
    results = search_fitgirl_games(query)
    if not results:
        print(f"No game repacks found matching \"{query}\".")
        return []

    print(f"\nFound {len(results)} result(s) for \"{query}\":")
    for idx, item in enumerate(results, 1):
        date_suffix = f" [{item['date']}]" if item.get('date') else ""
        print(f"  [{idx}] {item['title']}{date_suffix}")
        print(f"      {item['url']}")

    for _ in range(3):
        try:
            prompt = (
                f"\nSelect game number(s) (1-{len(results)}, e.g. 1 or 1,3 or 1-3 or 'all', 'q' to cancel): "
            )
            answer = input(prompt)
        except (EOFError, KeyboardInterrupt):
            print("\nSearch selection cancelled.")
            return []

        selected_indices = parse_search_selection(answer, len(results))
        if selected_indices is None:
            print(f"Invalid selection. Please enter number(s) between 1 and {len(results)}.")
            continue
        if not selected_indices:
            print("Search selection cancelled.")
            return []
        return [results[i]['url'] for i in selected_indices]

    print("Too many invalid attempts. Search cancelled.")
    return []


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


def _checkpoint_path(output_dir: str, job_name: str) -> str:
    cache_dir = os.path.join(output_dir, ".cache")
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"{job_name}_checkpoint.json")


def _load_checkpoint(path: str) -> dict[str, str]:
    """Load saved {clean_source_url: direct_url} map from a checkpoint file."""
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        links_map = data.get("resolved", {})
        if isinstance(links_map, dict):
            return {
                k: v for k, v in links_map.items()
                if isinstance(k, str) and is_valid_direct_link(v)
            }
    except Exception:
        pass
    return {}


def _save_checkpoint(path: str, source_desc: str, resolved_map: dict[str, str]):
    """Persist {clean_source_url: direct_url} checkpoint atomically."""
    payload = {
        "source": source_desc,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "resolved": resolved_map,
    }
    tmp_path = f"{path}.tmp"
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        pass


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
        '--search', '-s',
        nargs='+',
        type=str,
        help='Search FitGirl Repacks interactively from CLI (e.g. --search "planet zoo")',
    )
    parser.add_argument(
        '--concurrency', '-c',
        type=int,
        default=DEFAULT_CONCURRENCY,
        help=f'Number of parallel browser tabs for async link extraction (default: {DEFAULT_CONCURRENCY})',
    )
    parser.add_argument(
        '--lang', '-l',
        nargs='+',
        action='extend',
        type=str,
        help='Keep only specific selective language(s), e.g. --lang english or --lang english,japanese',
    )
    parser.add_argument(
        '--resume', '-r',
        action='store_true',
        help='Resume from saved checkpoint cache and skip already resolved part links',
    )
    parser.add_argument(
        '--updates', '-U',
        action='store_true',
        help='Also extract Game Update / Patch links into a separate <game>_updates.txt file',
    )
    parser.add_argument(
        '--updatesOnly',
        action='store_true',
        help='Extract ONLY Game Update / Patch links (<game>_updates.txt) and skip main repack files',
    )
    parser.add_argument(
        '--noBonus',
        action='store_true',
        help='Exclude bonus content links (files containing "fg-optional")',
    )
    parser.add_argument(
        '--noLanguage',
        action='store_true',
        help='Exclude all selective language links (files containing "fg-selective")',
    )
    args = parser.parse_args()

    if not args.url and not args.file and not args.search:
        parser.error("At least one of --url, --file, or --search must be specified.")

    if args.concurrency < 1:
        parser.error("--concurrency must be at least 1.")

    allowed_langs = _parse_lang_inputs(args.lang)
    if allowed_langs:
        print(f"Language filter active: keeping selective language(s) -> {', '.join(allowed_langs)}")

    fitgirl_urls: list[str] = []
    seen_fitgirl_urls: set[str] = set()
    # Each job is (job_stem, output_filename_stem, source_desc, sorted_links)
    direct_batches: list[tuple[str, str, str, list[str]]] = []

    def _add_fitgirl_url(u: str):
        normalized = u.rstrip('/')
        if normalized not in seen_fitgirl_urls:
            seen_fitgirl_urls.add(normalized)
            fitgirl_urls.append(u)

    # 0. Interactive CLI Search (--search)
    if args.search:
        query_str = " ".join(args.search).strip()
        if query_str:
            searched_urls = await asyncio.to_thread(interactive_search_flow, query_str)
            for u in searched_urls:
                _add_fitgirl_url(u)

    # 1. Collect URLs from --url
    cli_urls = _parse_url_inputs(args.url)
    cli_direct_links: list[str] = []
    for u in cli_urls:
        if _is_fuckingfast_url(u):
            cli_direct_links.append(u)
        else:
            _add_fitgirl_url(u)

    if cli_direct_links:
        filtered_cli = filter_fitgirl_links(
            cli_direct_links,
            exclude_bonus=args.noBonus,
            exclude_language=args.noLanguage,
            allowed_langs=allowed_langs,
        )
        if filtered_cli:
            direct_batches.append((
                "fitgirl_links",
                "fitgirl_links.txt",
                "CLI direct links",
                sort_fuckingfast_links(filtered_cli),
            ))

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
                filtered_ff = filter_fitgirl_links(
                    file_ff_links,
                    exclude_bonus=args.noBonus,
                    exclude_language=args.noLanguage,
                    allowed_langs=allowed_langs,
                )
                raw_stem = _sanitize_filename(os.path.splitext(os.path.basename(filepath))[0])
                # If user passed a *_failed.txt file, strip _failed suffix for output
                if raw_stem.endswith("_failed"):
                    raw_stem = raw_stem[:-7] or "fitgirl"
                out_txt = f"{raw_stem}.txt" if raw_stem.endswith(("_links", "_updates")) else f"{raw_stem}_links.txt"
                job_stem = os.path.splitext(out_txt)[0]
                if filtered_ff:
                    direct_batches.append((
                        job_stem,
                        out_txt,
                        f"File: {filepath}",
                        sort_fuckingfast_links(filtered_ff),
                    ))

    # 3. Scrape FitGirl repack pages concurrently (preserving URL order)
    jobs: list[tuple[str, str, str, list[str]]] = []
    if fitgirl_urls:
        print(f"Fetching {len(fitgirl_urls)} FitGirl repack page(s)...")
        scraped_pages = await asyncio.gather(
            *(
                asyncio.to_thread(
                    scrape_fitgirl_page,
                    u,
                    args.noBonus,
                    args.noLanguage,
                    allowed_langs,
                )
                for u in fitgirl_urls
            )
        )
        for u, (main_links, update_links) in zip(fitgirl_urls, scraped_pages):
            slug = _slug_from_url(u)
            if not args.updatesOnly:
                if main_links:
                    jobs.append((f"{slug}_links", f"{slug}_links.txt", u, main_links))
                else:
                    print(f"No main FuckingFast links found on: {u}")

            if args.updates or args.updatesOnly:
                if update_links:
                    jobs.append((
                        f"{slug}_updates",
                        f"{slug}_updates.txt",
                        f"{u} [Game Updates]",
                        update_links,
                    ))
                else:
                    print(f"No FuckingFast game update links found on: {u}")

    jobs.extend(direct_batches)

    if not jobs:
        print("No FuckingFast links found to process.")
        return

    output_dir = os.path.join(os.getcwd(), "output")
    os.makedirs(output_dir, exist_ok=True)
    used_filenames: set[str] = set()

    def _allocate_output_paths(job_stem: str, desired_txt: str) -> tuple[str, str, str]:
        base_stem = job_stem
        candidate_txt = desired_txt
        counter = 2
        while candidate_txt.lower() in used_filenames:
            base_stem = f"{job_stem}_{counter}"
            candidate_txt = f"{base_stem}.txt"
            counter += 1
        used_filenames.add(candidate_txt.lower())
        out_file = os.path.join(output_dir, candidate_txt)
        failed_prefix = base_stem[:-6] if base_stem.endswith("_links") else base_stem
        failed_file = os.path.join(output_dir, f"{failed_prefix}_failed.txt")
        ckpt_file = _checkpoint_path(output_dir, base_stem)
        return out_file, failed_file, ckpt_file

    total_jobs = len(jobs)
    summary_rows: list[tuple[str, int, int, str]] = []

    print(
        f"\nStarting async browser extraction across {total_jobs} target(s) "
        f"(concurrency={args.concurrency}, resume={args.resume})..."
    )

    try:
        async with FuckingFastBatchExtractor(concurrency=args.concurrency) as extractor:
            for job_idx, (job_stem, desired_txt, source_desc, links) in enumerate(jobs, 1):
                print(f"\n[{job_idx}/{total_jobs}] Target: {source_desc}")
                output_file, failed_file, ckpt_file = _allocate_output_paths(job_stem, desired_txt)

                # Always load existing checkpoint so incremental saves preserve prior entries;
                # only skip already-resolved links when --resume is enabled.
                checkpoint_map: dict[str, str] = _load_checkpoint(ckpt_file)

                pending_indices: list[int] = []
                pending_links: list[str] = []
                for idx, src_link in enumerate(links):
                    clean_u = src_link.split('#', 1)[0].strip()
                    if args.resume and is_valid_direct_link(checkpoint_map.get(clean_u)):
                        continue
                    pending_indices.append(idx)
                    pending_links.append(src_link)

                cached_count = len(links) - len(pending_links)
                if args.resume and cached_count > 0:
                    print(
                        f"Resuming from checkpoint: {cached_count}/{len(links)} link(s) already resolved, "
                        f"{len(pending_links)} remaining..."
                    )
                else:
                    print(f"Extracting {len(links)} ordered part/file link(s)...")

                def _on_link_resolved(src_l: str, direct_l: str):
                    clean_key = src_l.split('#', 1)[0].strip()
                    checkpoint_map[clean_key] = direct_l
                    _save_checkpoint(ckpt_file, source_desc, checkpoint_map)

                extracted_pending: dict[int, str] = {}
                if pending_links:
                    pending_results = await extractor.process_links(
                        pending_links,
                        on_progress=_on_link_resolved,
                    )
                    for orig_idx, res in zip(pending_indices, pending_results):
                        extracted_pending[orig_idx] = res

                # Assemble all links in strict original part order
                final_links: list[str] = []
                for idx, src_link in enumerate(links):
                    if idx in extracted_pending:
                        final_links.append(extracted_pending[idx])
                    else:
                        clean_u = src_link.split('#', 1)[0].strip()
                        final_links.append(checkpoint_map.get(clean_u, "Download link not found"))

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
                    with open(failed_file, 'w', encoding='utf-8') as ff:
                        for _, src_link, _ in failed_parts:
                            ff.write(f"{src_link}\n")
                    print(f"Warning - {len(failed_parts)} part(s) failed to resolve:")
                    for part_num, src_link, reason in failed_parts:
                        print(f"  - Part #{part_num}: {src_link} ({reason})")
                    print(f"Failed source links saved to: {failed_file}")
                    print("Tip: Re-run with --resume (or --file <failed_file>) to retry only failed parts.")
                else:
                    if os.path.isfile(failed_file):
                        try:
                            os.remove(failed_file)
                            print(f"Cleaned up previous failed-links file: {failed_file}")
                        except OSError:
                            pass

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
