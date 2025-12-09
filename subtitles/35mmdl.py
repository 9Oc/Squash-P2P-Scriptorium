#!/usr/bin/env python3
"""
Dependencies:
    pip install requests rich git+https://github.com/vevv/subby.git
Usage:
    35mmdl.py <page-url>
    
Set TMDB_API_KEY to your TMDB API key.
Set OUTPUT_DIR to your desired output directory.
"""
from __future__ import annotations

import argparse
import re
import shutil
import unicodedata
import urllib.parse
from pathlib import Path

import requests
from rich import print
from rich.console import Console

from subby import CommonIssuesFixer, WebVTTConverter

TMDB_API_KEY = "YOUR_TMDB_API_KEY"  # <-- your TMDB API key
OUTPUT_DIR = r"YOUR/OUTPUT/DIRECTORY"  # <-- your desired output directory

PRODUCT_API_REGEX = re.compile(
    r"/umbraco/api/products/(\d+)(?:\b|/|\?)", re.IGNORECASE)
CMS_BASE_URL = "https://cms.35mm.online"

LANG_MAP = {
    "pol": "pl",
    "eng": "en-US",
    "qtp": "pl[sdh]",
}

console = Console(color_system="truecolor")


class TMDBMovie:
    def __init__(self, id, imdb_id, title, original_title, year, duration,):
        self.id = id
        self.imdb_id = imdb_id
        self.title = title
        self.original_title = original_title
        self.year = year
        self.duration = duration

    def __repr__(self):
        return f"TMDBMovie(id={self.id}, title='{self.title}', original_title='{self.original_title}', year={self.year}, duration={self.duration}"

    @staticmethod
    def sanitize(text):
        """Return a filesystem-safe version of a string."""
        if not text:
            return ""
        text = re.sub(r'[\/\\:\*\?"<>\|\-—·.,^]+', '', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    @staticmethod
    def make_windows_safe(text: str, folder: bool) -> str:
        """
        Make a sanitized movie name safe for Windows filenames.
        Appends '_' to any reserved Windows device names (CON, PRN, AUX, NUL, COM1–COM9, LPT1–LPT9)
        while keeping the rest of the name intact.
        """
        reserved_names = {
            "CON", "PRN", "AUX", "NUL",
            "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
            "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
        }

        # split by dot to check each component
        if folder:
            parts = text.split()
        else:
            parts = text.split(".")
        if parts and parts[0].upper() in reserved_names:
            parts[0] += "_"
        join = " " if folder else "."
        return join.join(parts)


def get_tmdbmovie(movie_id: str) -> TMDBMovie | None:
    """Builds a TMDBMovie object from the given movie ID."""
    url = f"https://api.themoviedb.org/3/movie/{movie_id}"
    params = {"api_key": TMDB_API_KEY}

    def fetch_with_retry(url, params, timeout=5, retries=1):
        """Fetch URL with retry"""
        for attempt in range(retries + 1):
            try:
                r = requests.get(url, params=params, timeout=timeout)
                r.raise_for_status()
                return r
            except Exception as e:
                if attempt == retries:
                    raise

    try:
        r_main = fetch_with_retry(url, params)

        # get main movie info
        j = r_main.json()

        imdb_id = j.get("imdb_id") or None
        title = j.get("title") or None
        original_title = j.get("original_title") or None
        duration = j.get("runtime") or None
        if duration:
            duration = duration * 60  # convert duration to seconds

        # extract year from release date
        release_date = j.get("release_date") or j.get("first_air_date") or None
        year = None
        if release_date:
            match = re.match(r'(\d{4})', release_date)
            if match:
                year = int(match.group(1))

        return TMDBMovie(
            id=movie_id,
            imdb_id=imdb_id,
            title=title,
            original_title=original_title,
            year=year,
            duration=duration,
        )

    except Exception as e:
        return None


def search_tmdb_movie(title: str, year: int | None = None) -> TMDBMovie | None:
    """
    Search TMDB by title and year to find the best matching movie.
    Returns a full TMDBMovie object if a good match is found.
    If search with year fails, retries with year+1.
    If second search fails, retries a final time without year.
    """
    url = "https://api.themoviedb.org/3/search/movie"
    params = {
        "api_key": TMDB_API_KEY,
        "query": title,
        "language": "pl"
    }
    if year:
        params["year"] = year

    try:
        r = requests.get(url, params=params, timeout=7)
        r.raise_for_status()
        data = r.json()
        results = data.get("results", [])

        # if no results and we had a year, retry without year
        if not results and year:
            year = int(year)
            year += 1
            params["year"] = year
            r = requests.get(url, params=params, timeout=7)
            r.raise_for_status()
            data = r.json()
            results = data.get("results", [])
        # if no results again and we had a year, retry without year
        if not results and year:
            params.pop("year")  # remove year from params
            r = requests.get(url, params=params, timeout=7)
            r.raise_for_status()
            data = r.json()
            results = data.get("results", [])

        if not results:
            return None

        # use the first result as the best match
        best_match = results[0]
        movie_id = best_match.get("id")
        if not movie_id:
            return None

        # build TMDBMovie object
        return get_tmdbmovie(str(movie_id))

    except Exception as e:
        print(f"Error searching TMDB: {e}")
        return None


def normalize_subtitle_url(url: str) -> str:
    """
    Fix and normalize the given subtitle URL.
    This is necessary because the URLs in the JSON dict are relative
    and do not contain the http/https scheme.
    """
    u = url.strip()
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/"):
        return urllib.parse.urljoin(CMS_BASE_URL, u)
    parsed = urllib.parse.urlparse(u)
    if not parsed.scheme:
        return "https://" + u.lstrip("/")
    return u


def fetch_playlist(session: requests.Session, product_id: str, referer: str = None) -> dict:
    """Fetch the playlist JSON dict for the given product ID."""
    playlist_url = f"{CMS_BASE_URL}/umbraco/api/products/{product_id}/videos/playlist?platform=BROWSER&videoType=MOVIE"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.149 Safari/537.36"
    }
    if referer:
        headers["Referer"] = referer
    r = session.get(playlist_url, headers=headers, timeout=20)
    r.raise_for_status()
    return r.json()


def download_subtitles(session: requests.Session, playlist_json: dict, base_name: str, outdir: Path) -> list[Path]:
    """Download subtitles from the given playlist JSON dict."""
    subtitles = playlist_json.get("subtitles") or []
    saved_files: list[Path] = []
    outdir.mkdir(parents=True, exist_ok=True)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.149 Safari/537.36"
    }
    with console.status(pluralize_numbers(f"[green][35MM][/green] Downloading {len(subtitles)} subtitle"), spinner="dots", spinner_style="white", speed=0.9):
        for entry in subtitles:
            raw = entry.get("url") or entry.get("src") or ""
            lang = (entry.get("language") or entry.get("lang") or "").strip()
            if not raw:
                continue
            url = normalize_subtitle_url(raw)
            try:
                request = session.get(url, headers=headers, timeout=15)
                request.raise_for_status()
                # map language tags
                lang_key = lang.lower()
                if lang_key in LANG_MAP:
                    lang_tag = LANG_MAP[lang_key]
                elif lang:
                    lang_tag = lang
                else:
                    lang_tag = "und"
                # build filename: Movie.Name.Year.35mm.WEB.Language_tag.vtt
                filename = f"{base_name}.35mm.WEB.{lang_tag}.vtt"
                outpath = outdir / filename
                with open(outpath, "wb") as fh:
                    fh.write(request.content)
                saved_files.append(outpath)
            except Exception as e:
                print(f"Failed to download subtitle {url}: {e}")
    return saved_files


def get_subtitle_files(directory: str | Path, extension: str | None = None) -> list[Path]:
    """Get all subtitle files in the specified directory. If extension is None, get all .srt and .vtt"""
    path = Path(directory)
    if extension is None:
        return list(path.glob("*.srt")) + list(path.glob("*.vtt"))
    return list(path.glob(f"*.{extension}"))


def convert_vtt_to_srt(directory: str | Path):
    """Convert all VTT files to SRT format in the given directory."""
    directory = Path(directory)
    converter = WebVTTConverter()
    vtt_files = get_subtitle_files(directory, "vtt")

    for vtt in vtt_files:
        output_srt = directory / (vtt.stem + ".srt")
        if output_srt.exists():
            continue

        srt = converter.from_file(vtt)
        srt.save(output_srt)
        vtt.unlink()


def fix_common_issues(directory: str | Path):
    """Run common issues fixer on all SRT files in the specified directory."""
    directory = Path(directory)
    fixer = CommonIssuesFixer()
    srt_files = get_subtitle_files(directory, "srt")
    for srt_file in srt_files:
        srt, status = fixer.from_file(srt_file)
        fixed_srt_file = srt_file.with_name(
            srt_file.stem + "_fix" + srt_file.suffix)
        srt.save(fixed_srt_file)
        srt_file.unlink()
        fixed_srt_file.rename(srt_file)


def make_safe_filename(title: str, year: str, folder: bool = False) -> str:
    """
    Build safe base name using user's TMDBMovie.* helpers if available,
    otherwise fall back to the internal sanitizer.
    Expected final base: Movie.Name.Year
    """
    try:
        safe = TMDBMovie.sanitize(title).replace(" ", ".")
        safe = re.sub(r"\.+", ".", safe).strip(".")
        safe = TMDBMovie.make_windows_safe(safe, folder=folder)
    except Exception:
        safe = title

    # append year if available
    if year:
        base = f"{safe}.{year}"
    else:
        base = f"{safe}"
    # collapse muiltiple dots
    base = re.sub(r"\.+", ".", base).strip(".")
    return base


def get_alpha_folder(title: str) -> str:
    """
    Returns the alphabetical folder name (A-Z or 0-9) based on the first character of the title.
    Special characters and numbers go into '0-9'.
    """
    SPECIAL_BUCKET = r"1-9+$@.([¡¿!#"
    if not title:
        return SPECIAL_BUCKET

    title = title.lstrip("\ufeff\u200b\u200c\u200d\xa0")
    if not title:
        return SPECIAL_BUCKET
    # get first character
    first_char = title[0].upper()
    # strip accent from first character
    normalized = unicodedata.normalize("NFD", first_char)
    base_char = normalized[0].upper()

    # check if it's A-Z
    if base_char.isalpha() and 'A' <= base_char <= 'Z':
        return base_char

    return SPECIAL_BUCKET


def create_movie_folder(base_dir: str | Path, title: str, year: str | int, movie_id: str | int) -> Path:
    # sanitize title for filesystem
    if not title:
        title = "Unknown"
    safe_title = re.sub(r'[\/\\\:\*\?"<>\|]+', '', title).strip()
    safe_title = TMDBMovie.make_windows_safe(safe_title, folder=True)

    # get the alphabetical parent folder
    alpha_folder = get_alpha_folder(title)

    folder_name = f"{safe_title} ({year})"
    if movie_id:
        folder_name += f" [{movie_id}]"
    path = Path(base_dir) / alpha_folder / folder_name
    path.mkdir(parents=True, exist_ok=True)
    return path


def move_srt_files_to_folder(directory: Path, destination: Path) -> list[Path]:
    """
    Move all .srt files currently in <directory> to <destination>.
    Args:
        directory: Path object or string for source directory
        destination: Path object or string for destination folder
    Returns:
        list of destination paths for moved files
    """
    directory = Path(directory)
    destination = Path(destination)
    moved = []

    if not directory.exists():
        return moved

    srt_files = get_subtitle_files(directory, "srt")

    for file_path in srt_files:
        dest_path = destination / file_path.name

        # if destination exists, append a number
        if dest_path.exists():
            stem = file_path.stem
            suffix = file_path.suffix
            i = 1
            while True:
                new_name = f"{stem}_{i}{suffix}"
                dest_path = destination / new_name
                if not dest_path.exists():
                    break
                i += 1

        shutil.move(str(file_path), str(dest_path))
        moved.append(dest_path)

    return moved


def pluralize_numbers(text: str) -> str:
    """
    Adds 's' to a word following a number (integer or float)
    if the number is not ±1. Works even if Rich markup tags
    like [/orange1] appear between the number and the word.
    """
    pattern = re.compile(
        r'\b(-?\d+(?:\.\d+)?)'        # number
        # optional Rich tags, e.g. [orange1], [/orange1]
        r'(?:\[[^\]]+\])*'
        r'\s+([A-Za-z]+)\b'           # the word itself
    )

    def replacer(match):
        number = float(match.group(1))
        word = match.group(2)
        # add 's' only if not ±1
        if abs(number) != 1:
            # replace only the word part with pluralized one
            return match.group(0)[:-len(word)] + word + "s"
        return match.group(0)

    return pattern.sub(replacer, text)


def main():
    parser = argparse.ArgumentParser(
        description="Use Playwright to capture product XHR, parse title/year, and download subtitles with formatted filenames.")
    parser.add_argument("page_url", help="Page URL to open")
    args = parser.parse_args()

    outdir = Path(OUTPUT_DIR)
    page_url = args.page_url

    api_url = "https://cms.35mm.online/umbraco/api/content"

    # headers required by the API
    headers = {
        'X-Origin-Url': page_url,
        'X-Language': 'pl-pl',
        'X-Edutype': 'null'
    }
    console.print(
        f"[green][35MM][/green] Making api request for page: {page_url}")
    response = requests.get(api_url, headers=headers)

    # check if successful
    if response.status_code == 200:
        data = response.json()
        # get the product ID (atdId)
        pid = data['content']['atdId']

        # get movie info
        title = data['content']['title']
        year = data['content']['year']
        console.print(
            f"[green][35MM][/green] Parsed movie details - {title} ({year}) pid: {pid}")
    else:
        print(f"Error: {response.status_code}")
        print(response.text)
        return

    if not pid:
        console.print(
            "[yellow][35MM][/yellow] No pid found.")
        return

    movie = None
    with console.status(f"[green][TMDB][/green] Building TMDBMovie object", spinner="dots", spinner_style="white", speed=0.9):
        movie = search_tmdb_movie(title or "", int(year) if year else None)
        if movie:
            console.print(
                f"[green][TMDB][/green] Successfully built TMDBMovie object: {movie.title} ({movie.year}) [{movie.id}]")
        else:
            console.print(
                f"[yellow][TMDB][/yellow] Could not find a matching TMDB movie for title={title!r}, year={year!r}")

    # build safe base filename (Movie.Name.Year)
    base_name = None
    tmdb_id = None
    if movie:
        title = movie.title
        year = movie.year
        tmdb_id = movie.id
    else:
        if not title:
            # fallback to product id as base
            base_name = f"product {pid}"

    base_name = make_safe_filename(
        title, str(year) if year else "", folder=False)

    # fetch playlist and download subtitles
    session = requests.Session()
    with console.status(f"[green][35MM][/green] Fetching playlist", spinner="dots", spinner_style="white", speed=0.9):
        try:
            playlist_json = fetch_playlist(session, pid)
        except Exception as e:
            console.print(
                f"[yellow][35MM][/yellow] Failed to fetch playlist JSON: {e}")
            return
    console.print(pluralize_numbers(
        f"[green][35MM][/green] Found subtitle playlist with [orange1]{len(playlist_json.get('subtitles', []))}[/orange1] subtitle"))
    saved = download_subtitles(session, playlist_json, base_name, outdir)
    if saved:
        console.print(
            f"[green][35MM][/green] Saved [orange1]{len(saved)}[/orange1] subtitles to {outdir.resolve()}")
    else:
        console.print(
            f"[yellow][35MM][/yellow] No subtitles available for download for page: [dodger_blue1]{page_url}[/dodger_blue1]")

    with console.status(f"[green][CLEANUP][/green] Running cleanup tasks", spinner="dots", spinner_style="white", speed=0.9):
        convert_vtt_to_srt(outdir)
        fix_common_issues(outdir)

        srt_files = get_subtitle_files(outdir, "srt")
        if srt_files:
            movie_folder = create_movie_folder(
                outdir, title, year, tmdb_id)

            mm_folder = movie_folder / "35mm"
            mm_folder.mkdir(parents=True, exist_ok=True)

            moved = move_srt_files_to_folder(outdir, mm_folder)
            console.print(pluralize_numbers(
                f"[green][CLEANUP][/green] Moved [orange1]{len(moved)}[/orange1] file to [dodger_blue1]{mm_folder}[/dodger_blue1]"))


if __name__ == "__main__":
    main()
