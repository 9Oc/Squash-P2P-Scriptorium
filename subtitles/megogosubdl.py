#!/usr/bin/env python3
"""
Download subtitles from Megogo videos.

Dependencies:
    pip install aiohttp beautifulsoup4 lxml rich yarl git+https://github.com/vevv/subby.git

Usage:
    python megogosubdl.py <megogo_url>
"""

import argparse
import asyncio
import base64
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import aiohttp
from bs4 import BeautifulSoup
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from subby import CommonIssuesFixer, SAMIConverter, SDHStripper, SMPTEConverter, WebVTTConverter
from tmdbwrapper.tmdbmovie import TMDBMovie
from yarl import URL

# output directory for downloaded subtitles
OUTPUT_DIR = r"E:\.megogo"

NUMBERED_SUFFIX = re.compile(r"^(.*?)-(\d{1,2})(\.[^.]+)?$", re.IGNORECASE)
RESERVED_DEVICE_NAMES = {
    "CON","PRN","AUX","NUL",
    "COM1","COM2","COM3","COM4","COM5","COM6","COM7","COM8","COM9",
    "LPT1","LPT2","LPT3","LPT4","LPT5","LPT6","LPT7","LPT8","LPT9"
}

console = Console(color_system="truecolor")
common_issues_fixer = CommonIssuesFixer()
stripper = SDHStripper()
sami_converter = SAMIConverter()
smpte_converter = SMPTEConverter()
vtt_converter = WebVTTConverter()


# megogo api url
# https://megogo.net/wb/videoEmbed_v3/stream?lang={lang}&obj_id={video_id}&drm_type=modular
class MegogoClient:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.connector = aiohttp.TCPConnector(limit=50)
        self.timeout = aiohttp.ClientTimeout(total=60)
        self.headers = {
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Expires": "0",
            "Pragma": "no-cache",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/145.0.0.0 Safari/537.36"
            ),
            "X-Requested-With": "XMLHttpRequest",
        }
        self.session = aiohttp.ClientSession(connector=self.connector, headers=self.headers, timeout=self.timeout)

    def _get_csrf_from_play_session(self, video_url: str) -> str | None:
        """
        Extract csrf token (JWT) from PLAY_SESSION cookie.
        Returns token string or None.
        """
        # filter_cookies needs a URL to decide domain/path matching
        cookies = self.session.cookie_jar.filter_cookies(URL(video_url))
        play_cookie = cookies.get("PLAY_SESSION")
        if not play_cookie:
            return None
        jwt = play_cookie.value
        try:
            parts = jwt.split(".")
            if len(parts) < 2:
                return None
            payload_b64 = parts[1]
            # base64url decode, pad if needed
            rem = len(payload_b64) % 4
            if rem:
                payload_b64 += "=" * (4 - rem)
            payload_json = base64.urlsafe_b64decode(payload_b64.encode()).decode()
            payload = json.loads(payload_json)
            # token may be under payload['data']['csrfToken'] or payload['csrfToken']
            token = None
            if isinstance(payload, dict):
                token = payload.get("data", {}).get("csrfToken") or payload.get("csrfToken")
            return token
        except Exception:
            return None

    async def _ensure_csrf(self, video_url: str) -> None:
        """
        Ensure session has cookies and a csrf token header set. If PLAY_SESSION cookie
        isn't present, fetch the video_url page once to get cookies, then extract token.
        """
        if not self.session.cookie_jar.filter_cookies(video_url).get("PLAY_SESSION"):
            # try HEAD following redirects
            try:
                async with self.session.head(video_url, headers={"Referer": video_url}, allow_redirects=True) as resp:
                    # no body to read for HEAD, context manager ensures response is closed
                    pass
            except Exception:
                pass
            token = self._get_csrf_from_play_session(video_url)
            if token:
                return token
            # fetch page HTML (will set cookies via Set-Cookie on response)
            try:
                async with self.session.get(video_url, headers={"Referer": video_url}) as resp:
                    # we don't need page text here; cookies are stored in session.cookie_jar
                    await resp.text()  # consume response to allow cookie processing
            except Exception:
                # ignore errors; token extraction will fail gracefully if cookie not present
                pass

        return self._get_csrf_from_play_session(video_url)

    def _extract_video_id(self, url: str) -> str:
        """Extract the numeric video ID from a Megogo URL string."""
        match = re.search(r"/view/(\d+)", url)
        if not match:
            raise ValueError(f"Could not extract video ID from URL: {url}")
        return match.group(1)

    async def _fetch(self, url: str, headers: dict | None = None, response_type: str = "text", max_retries: int = 3) -> str:
        """Generic async fetch for text."""
        if response_type not in ("text", "bytes", "json"):
            raise ValueError(f"Invalid response_type: {response_type}, must be 'json', 'text', or 'bytes'")
        merged_headers = {**(self.headers or {}), **(headers or {})}
        for attempt in range(max_retries + 1):  # +1 to include initial attempt
            async with self.session.get(url, headers=merged_headers) as resp:
                try:
                    resp.raise_for_status()
                    if response_type == "text":
                        return await resp.text(encoding="utf-8", errors="replace")
                    elif response_type == "bytes":
                        return await resp.read()
                    elif response_type == "json":
                        return await resp.json()
                except Exception as e:
                    if attempt >= max_retries:
                        return None
                    console.print(
                        f"[red][MEGOGO CLIENT][/] Failed to fetch url: {url}\n{e}\nRetrying in 5 seconds ({attempt + 1}/{max_retries})..."
                    )
                    await asyncio.sleep(5)

    async def _fetch_release_year(self, video_url: str) -> str | None:
        """
        Fetch the video page HTML and extract the release year from the
        <a class="video-year link-default"> element.
        Megogo's API does not provide the release year from what I saw, so we scrape from here instead.

        Returns the year as a string (e.g. "1943"), or None if not found.
        """
        html = await self._fetch(video_url)
        soup = BeautifulSoup(html, "lxml")
        year_tag = soup.find("a", class_="video-year")
        if year_tag:
            return year_tag.get_text(strip=True)
        return None

    async def _download_subtitle(self, subtitle: dict) -> Path | None:
        """Download a single subtitle and write its contents to a file."""
        filename = subtitle.get("filename")
        subtitle_text = await self._fetch(subtitle.get("url"))
        if subtitle_text is None:
            return None

        subtitle_text = subtitle_text.replace("\r\n", "\n")
        filepath = self.output_dir / filename
        filepath.write_text(subtitle_text, encoding="utf-8")
        return filepath

    async def download_subtitles(
        self, video_url: str, content_title: str | None = None, content_year: str | None = None
    ) -> list[Path]:
        # clean query params from URL
        video_url = urlunparse(urlparse(video_url)._replace(query=""))
        video_url = video_url.replace(r"/tab_comments", "")
        video_id = self._extract_video_id(video_url)
        console.print(f"[green][MEGOGO CLIENT][/] Video ID: [dodger_blue1]{video_id}[/]")

        api_url = f"https://megogo.net/wb/videoEmbed_v3/stream?lang=en&obj_id={video_id}&drm_type=modular"

        # fetch API response that contains subtitle dicts and metadata
        console.print(f"[green][MEGOGO CLIENT][/] Fetching metadata for {video_url}")
        api_headers = {"Referer": video_url}
        # megogo generates a csrf token and stores it in the PLAY_SESSION cookie.
        # on first request, the cookie isn't set so the API allows the request without it,
        # but on subsequent requests from the same session, the API will reject requests that don't include the token
        csrf_token = await self._ensure_csrf(video_url)
        if csrf_token:
            api_headers["csrf-token"] = csrf_token
        try:
            api_json = await self._fetch(api_url, headers=api_headers, response_type="json")
            #api_json = json.loads(api_text)
            year = content_year or await self._fetch_release_year(video_url)
        except Exception as e:
            console.print(f"[red]Error fetching API data:[/red] {e}")
            return []

        # extract subtitles and content title from API response
        video_json = api_json["data"]["widgets"]["videoEmbed_v3"]["json"]
        subtitles = video_json.get("subtitles", [])
        if not subtitles:
            console.print("[yellow][MEGOGO CLIENT][/] No subtitles available for download")
            return []
        title = content_title or video_json.get("title", video_id)
        console.print(f"[green][MEGOGO CLIENT][/] Title: [sea_green2]{title}[/] ([dodger_blue1]{year}[/])")
        console.print(f"[green][MEGOGO CLIENT][/] Found [orange1]{len(subtitles)}[/] subtitle(s)")

        subs = []
        used_filenames = set()
        for subtitle in subtitles:
            subtitle_language = subtitle.get("lang_iso_639_1")
            if subtitle_language == "en":
                subtitle_language = "en-US"
            subtitle_type = subtitle.get("display_name").lower()
            if "azerbaijani" in subtitle_type:
                subtitle_language = "az"
            if any(s in subtitle_type for s in ("forced", "auto", "авто")):
                subtitle_type = "[forced]"
                continue
            elif "sdh" in subtitle_type:
                subtitle_type = "[sdh]"
            else:
                subtitle_type = ""
            subtitle_url = subtitle.get("url")
            filename = sanitize_string(f"{title}.{year}.MEGOGO.WEB")
            filename += f".{subtitle_language}{subtitle_type}.srt"
            filepath = self.output_dir / filename
            filename = get_unique_filename(filepath, used_filenames).name
            subs.append(
                {
                    "language": subtitle_language,
                    "type": subtitle_type,
                    "url": subtitle_url,
                    "filename": filename,
                    "content_title": title,
                    "content_year": year,
                }
            )
        results = []
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task_id = progress.add_task("[green][MEGOGO CLIENT][/] Downloading subtitles", total=len(subs))
            subtitle_tasks = [asyncio.create_task(self._download_subtitle(subtitle)) for subtitle in subs]
            for i, finished in enumerate(asyncio.as_completed(subtitle_tasks)):
                try:
                    subtitle = await finished
                except Exception as e:
                    subtitle = e
                results.append(subtitle)
                progress.update(
                    task_id,
                    advance=1,
                    description=f"Downloading subtitles {i + 1}/{len(subtitle_tasks)}",
                )
        successes = 0
        for result in results:
            if isinstance(result, Path):
                successes += 1
        console.print(f"[green][MEGOGO CLIENT][/] Successfully downloaded [orange1]{successes}[/] subtitle(s)")
        return results


def sanitize_string(text: str, folder: bool = False) -> str:
    """
    Sanitizes a string to be safe for use as a file or folder name on Windows/macOS/Linux.

    Args:
        text (str): The string to sanitize.
        folder (bool): Whether the string is intended to be a folder name or filename. Defaults to False.
    Returns:
        str: The sanitized string, or an empty string if the input was Falsey.
    """
    if not text:
        return ""
    s = re.sub(r'[\x00-\x1f<>:"/\\|?*\x7f\xa0]+', " ", text).strip()  # strip invalid chars for Windows/macOS/Linux
    if folder:
        s = re.sub(r"\s+", " ", s)
        s = re.sub(r"[‐–—⁃]", "-", s)  # replace bad hyphens
    else:
        s = s.replace("…", ".")
        s = re.sub(r"\s+", ".", s)
        s = re.sub(r"\.+", ".", s)
        s = s.strip(".")
        s = re.sub(r"\.(?:-|‐|–|—|⁃)\.", ".", s)  # fix bad hyphen types
        s = s.replace(",.", ".")
    if os.name == "nt":
        s = make_windows_safe(s)
    return s.strip() or ""


def make_windows_safe(text: str) -> str:
    """
    Sanitize a string to be safe for Windows file names.
    Appends '_' to any reserved Windows device names (CON, PRN, AUX, NUL, COM1-COM9, LPT1-LPT9)
    if they would cause an OSError to be thrown by the filesystem.

    Args:
        text (str): The input string to sanitize.
    Returns:
        str: The sanitized string with reserved names modified to be safe for Windows file names.
    """
    # split by dot to check each component
    parts = text.split(".", 1)
    if parts and parts[0].rstrip(" .").upper() in RESERVED_DEVICE_NAMES:
        parts[0] += "_"
    return ".".join(parts)


def get_unique_filename(file_path: str | Path, used_filenames: set[str] = None) -> Path:
    """
    Get a unique filename by incrementing numeric suffixes if needed.
    If the filename ends with -N (1-2 digits), it increments N until no conflict.
    """
    file_path = Path(file_path)
    path_str = str(file_path)
    if used_filenames is None:
        used_filenames = set()

    # if the path doesn't exist and is not used, return as is
    if not file_path.exists() and path_str not in used_filenames:
        used_filenames.add(path_str)
        return file_path

    stem = file_path.stem
    m = NUMBERED_SUFFIX.match(stem)

    if m:
        # file already ends in -N, so we start incrementing from N+1
        main_stem = m.group(1)
        i = int(m.group(2)) + 1
    else:
        # file has no numeric suffix, so we start with -1
        main_stem = stem
        i = 1

    while True:
        new_file_path = file_path.parent / f"{main_stem}-{i}{file_path.suffix}"
        new_path_str = str(new_file_path)
        if not new_file_path.exists() and new_path_str not in used_filenames:
            used_filenames.add(new_path_str)
            return new_file_path

        i += 1


def get_subtitle_files(directory: str | Path, *extensions) -> list[Path]:
    """
    Get all subtitle files in the specified directory.
    If no extensions are given (or all given extensions are None/empty),
    defaults to returning a list of files with these extensions: dfxp, sami, srt, ttml, ttml2, vtt.
    Pass any number of extensions, e.g. get_subtitle_files(dir, "srt", ".ass", "VTT").
    Extensions are matched case-insensitively and may include or omit the leading dot.
    """
    path = Path(directory)

    # default subtitle extensions
    default_exts = {"dfxp", "sami", "srt", "ttml", "ttml2", "vtt"}

    # normalize provided extensions (skip None/empty)
    if not extensions or all(e is None or e == "" for e in extensions):
        allowed = default_exts
    else:
        allowed = {str(e).lstrip(".").lower() for e in extensions if e is not None and str(e) != ""}
    subtitle_files = []
    for ext in allowed:
        subtitle_files.extend(path.glob(f"*.{ext}"))
    return subtitle_files


def fix_common_issues(directory: str | Path):
    """
    Run common issues fixer on all .srt files in the specified directory.
    A single file may be given as an argument instead of a path to a folder.
    """
    if not directory:
        return
    directory = Path(directory)
    if directory.is_file():
        srt_files = [directory]
    else:
        srt_files = get_subtitle_files(directory, "srt")
    for srt_file in srt_files:
        srt, status = common_issues_fixer.from_file(srt_file)
        fixed_srt_file = srt_file.with_name(srt_file.stem + "_fix" + srt_file.suffix)
        srt.save(fixed_srt_file)
        srt_file.unlink()
        fixed_srt_file.rename(srt_file)


async def main():
    parser = argparse.ArgumentParser(description="Download subtitles from the given Megogo video URL.")
    parser.add_argument("url", help="Megogo video URL")
    args = parser.parse_args()
    client = MegogoClient(output_dir=Path(OUTPUT_DIR))
    url = args.url
    try:
        subtitles = await client.download_subtitles(url)
        if subtitles:
            with console.status(
                "[green][CLEANUP][/] Running cleanup tasks",
                spinner="dots",
                spinner_style="white",
                speed=0.9,
            ):
                for subtitle in subtitles:
                    if isinstance(subtitle, Path):
                        fix_common_issues(subtitle)
            console.print("[green][CLEANUP][/] Cleanup complete")
    finally:
        await client.session.close()


if __name__ == "__main__":
    asyncio.run(main())
