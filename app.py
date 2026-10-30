import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlparse
import requests
from bs4 import BeautifulSoup
from download_util import (
    DEFAULT_CONCURRENCY,
    FuckingFastBatchExtractor,
    format_part_label,
    friendly_error_message,
    get_final_download_fuckingfast_async,
    is_valid_direct_link,
    process_fuckingfast_links_batch,
    set_verbose_logging,
    sort_fuckingfast_links,
)

# Optional Rich library support with built-in ANSI/Unicode fallback
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import (
        BarColumn,
        MofNCompleteColumn,
        Progress,
        SpinnerColumn,
        TaskProgressColumn,
        TextColumn,
        TimeRemainingColumn,
    )
    from rich.table import Table
    from rich import box
    HAS_RICH = True
    _CONSOLE = Console()
except ImportError:
    HAS_RICH = False
    _CONSOLE = None

# Enable ANSI escape sequences on Windows terminals when using fallback renderer
if os.name == "nt":
    os.system("")

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
    'popular-repacks-of-the-year',
}

NON_GAME_TITLE_PREFIXES = (
    'upcoming repacks',
    'updates digest',
    'monthly digest',
    'donations',
    'repacks troubleshooting',
    'faq',
)


# ---------------------------------------------------------------------------
# Clean CLI UI Helper (Uses `rich` if installed, or clean ANSI/Unicode fallback)
# ---------------------------------------------------------------------------

class CLIUI:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    MAGENTA = "\033[95m"

    @classmethod
    def banner(cls):
        title = "FitGirl Direct Link Generator"
        subtitle = "Fast, automatic direct download link extractor for IDM & JDownloader"
        if HAS_RICH:
            _CONSOLE.print()
            _CONSOLE.print(
                Panel(
                    f"[bold cyan]{title}[/bold cyan]\n[dim]{subtitle}[/dim]",
                    border_style="cyan",
                    box=box.ROUNDED,
                    padding=(0, 2),
                )
            )
        else:
            width = max(len(title), len(subtitle)) + 4
            print(f"\n{cls.CYAN}╭{'─' * width}╮{cls.RESET}")
            print(f"{cls.CYAN}│{cls.RESET}  {cls.BOLD}{cls.CYAN}{title.ljust(width - 2)}{cls.RESET}{cls.CYAN}│{cls.RESET}")
            print(f"{cls.CYAN}│{cls.RESET}  {cls.DIM}{subtitle.ljust(width - 2)}{cls.RESET}{cls.CYAN}│{cls.RESET}")
            print(f"{cls.CYAN}╰{'─' * width}╯{cls.RESET}")

    @classmethod
    def info(cls, msg: str):
        if HAS_RICH:
            _CONSOLE.print(f"[cyan]ℹ[/cyan] {msg}")
        else:
            print(f"{cls.CYAN}ℹ{cls.RESET} {msg}")

    @classmethod
    def success(cls, msg: str):
        if HAS_RICH:
            _CONSOLE.print(f"[bold green]✔[/bold green] {msg}")
        else:
            print(f"{cls.GREEN}✔{cls.RESET} {msg}")

    @classmethod
    def warn(cls, msg: str):
        if HAS_RICH:
            _CONSOLE.print(f"[bold yellow]⚠[/bold yellow] [yellow]{msg}[/yellow]")
        else:
            print(f"{cls.YELLOW}⚠ {msg}{cls.RESET}")

    @classmethod
    def error(cls, msg: str):
        if HAS_RICH:
            _CONSOLE.print(f"[bold red]✖[/bold red] [red]{msg}[/red]")
        else:
            print(f"{cls.RED}✖ {msg}{cls.RESET}")

    @classmethod
    def section(cls, title: str):
        if HAS_RICH:
            _CONSOLE.print(f"\n[bold magenta]━━ {title} ━━[/bold magenta]")
        else:
            print(f"\n{cls.BOLD}{cls.MAGENTA}━━ {title} ━━{cls.RESET}")

    @classmethod
    def search_results_table(cls, query: str, results: list[dict[str, str]]):
        if HAS_RICH:
            table = Table(
                title=f"Search Results for '{query}' ({len(results)} found)",
                box=box.ROUNDED,
                border_style="cyan",
                header_style="bold cyan",
                show_lines=False,
            )
            table.add_column("#", style="bold yellow", justify="right", width=4)
            table.add_column("Game Title", style="bold white")
            table.add_column("Release Date", style="dim", width=16)
            for idx, item in enumerate(results, 1):
                table.add_row(str(idx), item["title"], item.get("date") or "-")
            _CONSOLE.print()
            _CONSOLE.print(table)
        else:
            print(f"\n{cls.BOLD}{cls.CYAN}Search Results for '{query}' ({len(results)} found):{cls.RESET}")
            print(f"{cls.DIM}{'─' * 72}{cls.RESET}")
            for idx, item in enumerate(results, 1):
                date_str = f" ({item['date']})" if item.get("date") else ""
                print(f"  {cls.YELLOW}[{idx}]{cls.RESET} {cls.BOLD}{item['title']}{cls.RESET}{cls.DIM}{date_str}{cls.RESET}")
                print(f"      {cls.DIM}{item['url']}{cls.RESET}")
            print(f"{cls.DIM}{'─' * 72}{cls.RESET}")

    @classmethod
    def summary_table(cls, summary_rows: list[tuple[str, int, int, str]]):
        if HAS_RICH:
            table = Table(
                title="Download Links Summary",
                box=box.ROUNDED,
                border_style="green",
                header_style="bold green",
            )
            table.add_column("Game / Source", style="bold white")
            table.add_column("Files Ready", justify="center")
            table.add_column("Saved Text File", style="cyan")
            for label, ok_cnt, total_cnt, out_path in summary_rows:
                status_style = "bold green" if ok_cnt == total_cnt else ("bold yellow" if ok_cnt > 0 else "bold red")
                table.add_row(label, f"[{status_style}]{ok_cnt}/{total_cnt}[/{status_style}]", out_path)
            _CONSOLE.print()
            _CONSOLE.print(table)
        else:
            print(f"\n{cls.BOLD}{cls.GREEN}━━ Download Links Summary ━━{cls.RESET}")
            for label, ok_cnt, total_cnt, out_path in summary_rows:
                color = cls.GREEN if ok_cnt == total_cnt else (cls.YELLOW if ok_cnt > 0 else cls.RED)
                print(f"  • {cls.BOLD}{label}{cls.RESET}: {color}{ok_cnt}/{total_cnt} files ready{cls.RESET} -> {cls.CYAN}{out_path}{cls.RESET}")

    @classmethod
    def idm_guide_box(cls):
        steps = (
            "1. Open Internet Download Manager (IDM)\n"
            "2. Click menu: Tasks -> Import -> From text file\n"
            "3. Choose your generated .txt file inside the 'output' folder\n"
            "4. Click 'Check All' -> 'OK' to start downloading!"
        )
        if HAS_RICH:
            _CONSOLE.print()
            _CONSOLE.print(
                Panel(
                    steps,
                    title="[bold green]Next Step: How to Download with IDM[/bold green]",
                    border_style="green",
                    box=box.ROUNDED,
                    padding=(0, 2),
                )
            )
        else:
            print(f"\n{cls.GREEN}╭── Next Step: How to Download with IDM ──────────────────────────╮{cls.RESET}")
            for line in steps.splitlines():
                print(f"{cls.GREEN}│{cls.RESET}  {line.ljust(63)}{cls.GREEN}│{cls.RESET}")
            print(f"{cls.GREEN}╰─────────────────────────────────────────────────────────────────╯{cls.RESET}")


class LiveExtractionProgress:
    """
    Context manager that renders a live progress bar during async extraction.
    Uses `rich.progress.Progress` when available, or a clean single-line ANSI bar.
    """

    def __init__(self, total: int, initial_completed: int = 0):
        self.total = max(1, total)
        self.completed = initial_completed
        self.status_text = "Starting..."
        self._rich_progress = None
        self._task_id = None
        self._start_time = time.time()

    def __enter__(self):
        if HAS_RICH:
            self._rich_progress = Progress(
                SpinnerColumn(),
                TextColumn("[bold cyan]{task.description}[/bold cyan]"),
                BarColumn(bar_width=28),
                MofNCompleteColumn(),
                TaskProgressColumn(),
                TimeRemainingColumn(),
                TextColumn("[dim]{task.fields[status]}[/dim]"),
                console=_CONSOLE,
                transient=False,
            )
            self._rich_progress.__enter__()
            self._task_id = self._rich_progress.add_task(
                "Fetching links",
                total=self.total,
                completed=self.completed,
                status=self.status_text,
            )
        else:
            self._render_ansi()
        return self

    def __exit__(self, exc_type, exc, tb):
        if HAS_RICH and self._rich_progress is not None:
            self._rich_progress.update(self._task_id, status="Done")
            self._rich_progress.__exit__(exc_type, exc, tb)
        else:
            sys.stdout.write("\n")
            sys.stdout.flush()

    def on_status(self, event: str, part_num: int, total_pending: int, message: str):
        if event in ("done", "failed"):
            self.completed += 1
            if event == "done":
                self.status_text = f"Ready: {message}"
            else:
                self.status_text = f"Failed: {message}"
        elif event == "rate_limit":
            self.status_text = message
        elif event == "retry":
            self.status_text = message
        else:
            self.status_text = f"Working on {message}..."

        if HAS_RICH and self._rich_progress is not None:
            self._rich_progress.update(
                self._task_id,
                completed=self.completed,
                status=self.status_text,
            )
        else:
            self._render_ansi()

    def _render_ansi(self):
        pct = min(100, int((self.completed / self.total) * 100))
        bar_len = 22
        filled = int((self.completed / self.total) * bar_len)
        bar = "█" * filled + "░" * (bar_len - filled)
        short_status = self.status_text[:44].ljust(44)
        line = (
            f"\r  {CLIUI.CYAN}[{bar}]{CLIUI.RESET} {CLIUI.BOLD}{pct:3d}%{CLIUI.RESET} "
            f"({self.completed}/{self.total} files) • {CLIUI.DIM}{short_status}{CLIUI.RESET}"
        )
        sys.stdout.write(line)
        sys.stdout.flush()


# ---------------------------------------------------------------------------
# Core Link Scraping, Filtering & Search Functions
# ---------------------------------------------------------------------------

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
    spoiler = a_tag.find_parent(class_=re.compile(r'\bsu-spoiler\b'))
    if spoiler:
        title_el = spoiler.find(class_=re.compile(r'\bsu-spoiler-title\b'))
        if title_el:
            title_text = title_el.get_text(" ", strip=True).lower()
            if any(k in title_text for k in ('game update', 'updates', 'patch', 'hotfix')):
                if 'download mirrors' not in title_text:
                    return True

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
        CLIUI.error(f"Could not open page {url}: {friendly_error_message(str(e))}")
        return [], []

    if response.status_code != 200:
        CLIUI.error(f"Could not open page {url} (HTTP {response.status_code})")
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
        CLIUI.error(f"Could not connect to FitGirl search: {friendly_error_message(str(e))}")
        return []

    if response.status_code != 200:
        CLIUI.error(f"FitGirl search returned HTTP {response.status_code}")
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
    CLIUI.info(f"Searching FitGirl Repacks for '{query}'...")
    results = search_fitgirl_games(query)
    if not results:
        CLIUI.warn(f"No games found matching '{query}'. Try a shorter keyword.")
        return []

    CLIUI.search_results_table(query, results)

    for _ in range(3):
        try:
            prompt = (
                f"\nEnter game number(s) to download (1-{len(results)}, e.g. 1 or 1,3 or 'all', 'q' to cancel): "
            )
            answer = input(prompt)
        except (EOFError, KeyboardInterrupt):
            print()
            CLIUI.warn("Search cancelled.")
            return []

        selected_indices = parse_search_selection(answer, len(results))
        if selected_indices is None:
            CLIUI.warn(f"Please enter valid number(s) between 1 and {len(results)}.")
            continue
        if not selected_indices:
            CLIUI.info("Search cancelled.")
            return []
        return [results[i]['url'] for i in selected_indices]

    CLIUI.warn("Too many invalid attempts. Search cancelled.")
    return []


def _parse_url_inputs(raw_urls: list[str] | None) -> list[str]:
    """Support space-separated and comma-separated URLs from --url."""
    if not raw_urls:
        return []
    parsed_urls: list[str] = []
    for item in raw_urls:
        for part in re.split(r'[,\s]+', item):
            u = part.strip()
            if u.startswith("http"):
                parsed_urls.append(u)
    return parsed_urls


# ---------------------------------------------------------------------------
# Checkpoint Management
# ---------------------------------------------------------------------------

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


def _save_checkpoint(
    path: str,
    source_desc: str,
    resolved_map: dict[str, str],
    all_links: list[str] | None = None,
    job_stem: str | None = None,
    desired_txt: str | None = None,
):
    """Persist checkpoint atomically so interrupted runs can be resumed easily."""
    payload = {
        "job_stem": job_stem or "",
        "desired_txt": desired_txt or "",
        "source": source_desc,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "all_links": all_links or [],
        "resolved": resolved_map,
    }
    tmp_path = f"{path}.tmp"
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        pass


def _list_resumable_checkpoints(output_dir: str) -> list[dict]:
    """Find saved checkpoints in output/.cache/ that can be resumed."""
    cache_dir = os.path.join(output_dir, ".cache")
    if not os.path.isdir(cache_dir):
        return []
    items: list[dict] = []
    for fname in sorted(os.listdir(cache_dir)):
        if not fname.endswith("_checkpoint.json"):
            continue
        fpath = os.path.join(cache_dir, fname)
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            all_links = data.get("all_links") or []
            resolved = {
                k: v for k, v in (data.get("resolved") or {}).items()
                if is_valid_direct_link(v)
            }
            if not all_links:
                continue
            done_cnt = sum(1 for l in all_links if l.split('#', 1)[0].strip() in resolved)
            items.append({
                "job_stem": data.get("job_stem") or fname[:-16],
                "desired_txt": data.get("desired_txt") or f"{fname[:-16]}.txt",
                "source": data.get("source") or fname[:-16],
                "all_links": all_links,
                "done_count": done_cnt,
                "total_count": len(all_links),
            })
        except Exception:
            continue
    return items


# ---------------------------------------------------------------------------
# Interactive Beginner Wizard (When `python app.py` is run without arguments)
# ---------------------------------------------------------------------------

def _prompt_filter_preferences(args):
    """Ask simple, optional filter questions in interactive mode."""
    try:
        lang_ans = input(
            "\nLanguage pack filter (e.g. 'english', 'none' to skip all, or press Enter for all): "
        ).strip()
        if lang_ans.lower() == "none":
            args.noLanguage = True
        elif lang_ans:
            args.lang = [lang_ans]

        bonus_ans = input("Skip optional bonus files (soundtracks, artbooks, videos)? [Y/n]: ").strip().lower()
        if bonus_ans in ("", "y", "yes"):
            args.noBonus = True

        upd_ans = input("Also extract Game Update / Patch links if available? [y/N]: ").strip().lower()
        if upd_ans in ("y", "yes"):
            args.updates = True
    except (EOFError, KeyboardInterrupt):
        print()


def _run_interactive_wizard(args, output_dir: str) -> list[tuple[str, str, str, list[str]]] | None:
    """
    Friendly interactive menu shown when the user runs `python app.py` without CLI flags.
    Returns any direct checkpoint jobs selected, or populates `args` and returns `[]`.
    Returns `None` if the user chose to exit.
    """
    print("\nHow would you like to get your download links?")
    print(f"  {CLIUI.YELLOW}[1]{CLIUI.RESET} Search for a game on FitGirl Repacks")
    print(f"  {CLIUI.YELLOW}[2]{CLIUI.RESET} Paste one or more FitGirl game URLs")
    print(f"  {CLIUI.YELLOW}[3]{CLIUI.RESET} Load links from a .txt file")
    print(f"  {CLIUI.YELLOW}[4]{CLIUI.RESET} Resume a previous download from saved progress")
    print(f"  {CLIUI.YELLOW}[0]{CLIUI.RESET} Exit")

    try:
        choice = input("\nChoose an option (0-4): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None

    if choice in ("0", "q", "quit", "exit", ""):
        CLIUI.info("Goodbye!")
        return None

    if choice == "1":
        try:
            q = input("Enter game name to search: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if not q:
            CLIUI.warn("No search keyword entered.")
            return None
        args.search = [q]
        _prompt_filter_preferences(args)
        return []

    if choice == "2":
        try:
            raw_u = input("Paste FitGirl URL(s) (separate multiple URLs with spaces or commas): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if not raw_u:
            CLIUI.warn("No URL entered.")
            return None
        args.url = [raw_u]
        _prompt_filter_preferences(args)
        return []

    if choice == "3":
        try:
            fpath = input("Enter path to your .txt file: ").strip().strip('"').strip("'")
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if not fpath:
            CLIUI.warn("No file path entered.")
            return None
        args.file = [fpath]
        return []

    if choice == "4":
        args.resume = True
        saved = _list_resumable_checkpoints(output_dir)
        if not saved:
            CLIUI.warn("No saved progress found in 'output/.cache/'.")
            try:
                raw_u = input("Paste the FitGirl URL you want to resume (or press Enter to cancel): ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return None
            if not raw_u:
                return None
            args.url = [raw_u]
            return []

        print("\nSaved downloads:")
        for idx, item in enumerate(saved, 1):
            status_tag = (
                "Completed" if item["done_count"] == item["total_count"]
                else f"{item['done_count']}/{item['total_count']} files ready"
            )
            print(f"  {CLIUI.YELLOW}[{idx}]{CLIUI.RESET} {item['job_stem']} ({status_tag}) — {item['source']}")

        try:
            sel = input(f"\nSelect number(s) to resume (1-{len(saved)}, or 'all'): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None

        chosen = parse_search_selection(sel, len(saved))
        if not chosen:
            CLIUI.info("Resume cancelled.")
            return None

        resumed_jobs: list[tuple[str, str, str, list[str]]] = []
        for i in chosen:
            c = saved[i]
            resumed_jobs.append((c["job_stem"], c["desired_txt"], c["source"], c["all_links"]))
        return resumed_jobs

    CLIUI.warn("Invalid menu option.")
    return None


# ---------------------------------------------------------------------------
# Main Entrypoint
# ---------------------------------------------------------------------------

async def async_main():
    parser = argparse.ArgumentParser(
        description='FitGirl Direct Link Generator — Fast, automatic direct download links for IDM & JDownloader'
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
        help=f'Number of parallel downloads to process at once (default: {DEFAULT_CONCURRENCY})',
    )
    parser.add_argument(
        '--lang', '-l',
        nargs='+',
        action='extend',
        type=str,
        help='Keep only specific language pack(s), e.g. --lang english or --lang english,japanese',
    )
    parser.add_argument(
        '--resume', '-r',
        action='store_true',
        help='Resume from saved progress and only fetch remaining files',
    )
    parser.add_argument(
        '--updates', '-U',
        action='store_true',
        help='Also extract Game Update / Patch links into a separate <game>_updates.txt file',
    )
    parser.add_argument(
        '--updatesOnly',
        action='store_true',
        help='Extract ONLY Game Update / Patch links (<game>_updates.txt) and skip main game files',
    )
    parser.add_argument(
        '--noBonus',
        action='store_true',
        help='Skip optional bonus content (soundtracks, artbooks, videos)',
    )
    parser.add_argument(
        '--noLanguage',
        action='store_true',
        help='Skip all selective language packs',
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show detailed technical logs for troubleshooting',
    )
    args = parser.parse_args()

    set_verbose_logging(args.verbose)
    CLIUI.banner()

    if args.concurrency < 1:
        CLIUI.error("--concurrency must be at least 1.")
        return

    output_dir = os.path.join(os.getcwd(), "output")
    os.makedirs(output_dir, exist_ok=True)

    wizard_jobs: list[tuple[str, str, str, list[str]]] = []
    # Launch interactive wizard if user ran `python app.py` with no input arguments
    if not args.url and not args.file and not args.search:
        if sys.stdin.isatty():
            wizard_res = await asyncio.to_thread(_run_interactive_wizard, args, output_dir)
            if wizard_res is None:
                return
            wizard_jobs.extend(wizard_res)
        else:
            parser.error("At least one of --url, --file, or --search must be specified.")

    allowed_langs = _parse_lang_inputs(args.lang)
    if allowed_langs:
        CLIUI.info(f"Language filter: keeping only {', '.join(allowed_langs)}")
    elif args.noLanguage:
        CLIUI.info("Language filter: skipping all selective language packs")

    if args.noBonus:
        CLIUI.info("Bonus filter: skipping optional bonus files")

    fitgirl_urls: list[str] = []
    seen_fitgirl_urls: set[str] = set()
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
                "Direct CLI Links",
                sort_fuckingfast_links(filtered_cli),
            ))

    # 2. Collect URLs from --file
    if args.file:
        for filepath in args.file:
            if not os.path.isfile(filepath):
                CLIUI.warn(f"File not found, skipping: {filepath}")
                continue
            CLIUI.info(f"Reading links from file: {filepath}")
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
                if raw_stem.endswith("_failed"):
                    raw_stem = raw_stem[:-7] or "fitgirl"
                out_txt = f"{raw_stem}.txt" if raw_stem.endswith(("_links", "_updates")) else f"{raw_stem}_links.txt"
                job_stem = os.path.splitext(out_txt)[0]
                if filtered_ff:
                    direct_batches.append((
                        job_stem,
                        out_txt,
                        os.path.basename(filepath),
                        sort_fuckingfast_links(filtered_ff),
                    ))

    # 3. Scrape FitGirl repack pages concurrently (preserving URL order)
    jobs: list[tuple[str, str, str, list[str]]] = list(wizard_jobs)
    if fitgirl_urls:
        CLIUI.info(f"Checking {len(fitgirl_urls)} FitGirl game page(s) for download links...")
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
                    CLIUI.success(f"Found {len(main_links)} main file(s) for '{slug}'")
                    jobs.append((f"{slug}_links", f"{slug}_links.txt", slug, main_links))
                else:
                    CLIUI.warn(f"No main FuckingFast links found on: {u}")

            if args.updates or args.updatesOnly:
                if update_links:
                    CLIUI.success(f"Found {len(update_links)} update/patch file(s) for '{slug}'")
                    jobs.append((
                        f"{slug}_updates",
                        f"{slug}_updates.txt",
                        f"{slug} (Game Updates)",
                        update_links,
                    ))
                else:
                    CLIUI.warn(f"No FuckingFast update/patch links found on: {u}")

    jobs.extend(direct_batches)

    if not jobs:
        CLIUI.warn("No download links found to process.")
        return

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

    CLIUI.info(
        f"Starting automatic link extractor ({args.concurrency} parallel workers)..."
    )

    try:
        async with FuckingFastBatchExtractor(concurrency=args.concurrency) as extractor:
            for job_idx, (job_stem, desired_txt, source_desc, links) in enumerate(jobs, 1):
                CLIUI.section(f"Target [{job_idx}/{total_jobs}]: {source_desc}")
                output_file, failed_file, ckpt_file = _allocate_output_paths(job_stem, desired_txt)

                # Load existing checkpoint so incremental saves preserve prior entries
                checkpoint_map: dict[str, str] = _load_checkpoint(ckpt_file)
                _save_checkpoint(
                    ckpt_file,
                    source_desc,
                    checkpoint_map,
                    all_links=links,
                    job_stem=job_stem,
                    desired_txt=desired_txt,
                )

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
                    if pending_links:
                        CLIUI.info(
                            f"Resuming saved progress: {cached_count} of {len(links)} file(s) already done. "
                            f"Fetching the remaining {len(pending_links)} file(s)..."
                        )
                    else:
                        CLIUI.success(f"All {len(links)} file(s) were already completed in your saved progress!")

                def _on_link_resolved(src_l: str, direct_l: str):
                    clean_key = src_l.split('#', 1)[0].strip()
                    checkpoint_map[clean_key] = direct_l
                    _save_checkpoint(
                        ckpt_file,
                        source_desc,
                        checkpoint_map,
                        all_links=links,
                        job_stem=job_stem,
                        desired_txt=desired_txt,
                    )

                extracted_pending: dict[int, str] = {}
                if pending_links:
                    with LiveExtractionProgress(total=len(links), initial_completed=cached_count) as progress_ui:
                        pending_results = await extractor.process_links(
                            pending_links,
                            on_progress=_on_link_resolved,
                            on_status=progress_ui.on_status,
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
                            failed_parts.append((part_num, src_link, friendly_error_message(str(direct_link))))

                if success_count == len(links):
                    CLIUI.success(f"Done! All {success_count}/{len(links)} direct download link(s) are ready.")
                else:
                    CLIUI.warn(f"Finished: {success_count} of {len(links)} direct download link(s) saved.")
                CLIUI.info(f"Saved to: {output_file}")

                if failed_parts:
                    with open(failed_file, 'w', encoding='utf-8') as ff:
                        for _, src_link, _ in failed_parts:
                            ff.write(f"{src_link}\n")
                    CLIUI.warn(f"{len(failed_parts)} file(s) could not be fetched right now:")
                    for part_num, src_link, reason in failed_parts:
                        short_name = format_part_label(src_link)
                        print(f"    • Part #{part_num} ({short_name}) — {reason}")
                    CLIUI.info(f"Missing links saved to: {failed_file}")
                    CLIUI.info("Tip: Run again with --resume to retry only the missing file(s).")
                else:
                    if os.path.isfile(failed_file):
                        try:
                            os.remove(failed_file)
                        except OSError:
                            pass

                summary_rows.append((source_desc, success_count, len(links), output_file))

        CLIUI.summary_table(summary_rows)
        CLIUI.idm_guide_box()

    except KeyboardInterrupt:
        print()
        CLIUI.warn("Process interrupted by user. Your progress has been saved — run with --resume to continue!")
    except Exception as e:
        CLIUI.error(f"Something went wrong: {friendly_error_message(str(e))}")


def main():
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
