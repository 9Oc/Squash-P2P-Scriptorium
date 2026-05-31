"""
version 1.03
Subtitle file-names should end with a . followed by the language tag.
For example: Juno.2007.AMZN.WEB.en-us.srt
Anything that comes before ".en-us" can be whatever you want.
If your .srt filenames do not end with a . followed by the language tag, then the synced files will not be alphabetically sorted and instead will have their filenames unchanged.

Dependencies:
pip install ffsubsync
ffmpeg https://ffmpeg.org/download.html
ffmpeg must be added to your PATH.
"""
import argparse
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from pathlib import Path

ALPHABETICAL_CODE_MAP = {
    "en-US": "american.en-US",
    "en-AU": "australian.en-AU",
    "en-GB": "british.en-GB",
    "en-CA": "canadian.en-CA",
    "sq": "albanian.sq",
    "eu": "basque.eu",
    "bn": "bengali.bn",
    "bs": "bosnian.bs",
    "bg": "bulgarian.bg",
    "zh-Hans": "chinese.simplified.zh-Hans",
    "zh-Hant": "chinese.traditional.zh-Hant",
    "yue-Hant": "chinese.cantonese.zh-Hant",
    "hr": "croatian.hr",
    "nl": "dutch.nl",
    "nl-BE": "dutch.nl-BE",
    "fi": "finnish.fi",
    "fr-FR": "french.parisian.fr-FR",
    "fr-CA": "french.quebec.fr-CA",
    "gl": "galacian.gl",
    "ka": "georgian.ka",
    "de": "german.1.de",
    "de-AT": "german.austrian.de-AT",
    "de-CH": "german.swiss.de-CH",
    "el": "greek.el",
    "is": "icelandic.is",
    "id": "indonesian.id",
    "ga": "irish.ga",
    "kn": "kannada.kn",
    "kk": "kazakh.kk",
    "ky": "kirghiz.ky",
    "lv": "latvian.lv",
    "lt": "lithuanian.lt",
    "lb": "luxembourgish.lb",
    "mk": "macedonian.mk",
    "ms": "malay.ms",
    "ml": "malayam.ml",
    "mr": "marathi.mr",
    "fa": "persian.fa",
    "pt-PT": "portuguese.pt-PT",
    "sr": "serbian.sr",
    "es-ES": "spain.es-ES",
    "es-419": "spanish.es-419",
    "tl": "tagalog.tl",
    "cy": "welsh.cy",
}
ALPHABETICAL_CODE_MAP_LOWER = {k.lower(): v for k, v in ALPHABETICAL_CODE_MAP.items()}

AUDIO_EXTENSIONS = [
    ".ac3", ".ec3", ".eac3", ".aac", ".flac", ".wav",
    ".thd", ".dts", ".dtshd", ".dtsma", ".opus", ".ogg",
    ".dtshr", ".mlp", ".w64"
]

PROGRESS_PATTERN = re.compile(r"^\s*\d{1,3}%\|.*$")
SRT_PATTERN = re.compile(
    r"\['([^']*?\.srt)'\]\.\.\.",
    re.DOTALL
)
SCORE_PATTERN = re.compile(r"score:\s*([0-9.]+)")
OFFSET_PATTERN = re.compile(r"offset seconds:\s*([0-9.\-]+)")
FRAMERATE_PATTERN = re.compile(r"framerate scale factor:\s*([0-9.]+)")


def make_box(title, lines):
    content = [title] + lines
    width = max(len(line) for line in content)

    box = [
        f"┌{'─' * (width + 2)}┐",
        f"│ {title.ljust(width)} │",
        f"├{'─' * (width + 2)}┤",
    ]

    for line in lines:
        box.append(f"│ {line.ljust(width)} │")

    box.append(f"└{'─' * (width + 2)}┘")

    return "\n".join(box)


def get_alphabetical_lang_code(lang_code: str) -> str:
    if not lang_code:
        return lang_code
    base_code = lang_code.split("[")[0]  # remove [sdh], [cc], or [forced] for mapping
    mapped = ALPHABETICAL_CODE_MAP_LOWER.get(base_code.lower(), base_code)
    # re-append [sdh], [cc], or [forced] if present
    if "[" in lang_code:
        mapped += lang_code[lang_code.index("["):]
    return mapped
    

def find_audio_file(directory: Path, specified: Path = None) -> Path:
    """
    Get the first audio file in the specified directory
    with an extension matching an extension in AUDIO_EXTENSIONS.
    """
    for ext in AUDIO_EXTENSIONS:
        files = list(directory.glob(f"*{ext}"))
        if files:
            return files[0].resolve()
    
    print(f"No audio file found in {directory} with extensions: {AUDIO_EXTENSIONS}")
    sys.exit(1)


def process_subtitle(mkv_file: Path, subtitle_file: Path, output_dir: Path, no_fix_framerate: bool = False):
    """Sync and rename (if needed) one subtitle file using ffsubsync."""
    filename = subtitle_file.stem
    parts = filename.split('.')
    lang_code = parts[-1] if len(parts) > 1 else None
    if not lang_code:
        output_file = output_dir / f"{filename}.srt"
    else:
        new_file_name = filename.rsplit('.', 1)[0]
        new_file_name = re.sub(r"\.+", ".", new_file_name).strip(".")
        alphabetical_lang_code = get_alphabetical_lang_code(lang_code)
        ENGLISH_CODES = {"en", "american.en-US", "australian.en-AU", "british.en-GB", "canadian.en-CA",
                         "en[sdh]", "american.en-US[sdh]", "australian.en-AU[sdh]", "british.en-GB[sdh]",
                         "canadian.en-CA[sdh]"}
        if alphabetical_lang_code in ENGLISH_CODES:
            alphabetical_lang_code = "_" + alphabetical_lang_code
        output_file = output_dir / f"{new_file_name}.{alphabetical_lang_code}.srt"
    

    cmd = [
        "ffs",
        str(mkv_file),
        "-i", str(subtitle_file),
        "-o", str(output_file),
    ]
    if no_fix_framerate:
        cmd.append("--no-fix-framerate")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        log = result.stdout.splitlines() + result.stderr.splitlines()
        filtered_output = "\n".join([line for line in log if not PROGRESS_PATTERN.match(line)])
        lines = []
        score = SCORE_PATTERN.search(filtered_output)
        if score:
            lines.append(f"score: {score.group(1)}")

        offset = OFFSET_PATTERN.search(filtered_output)
        if offset:
            lines.append(f"offset seconds: {offset.group(1)}")

        framerate = FRAMERATE_PATTERN.search(filtered_output)
        if framerate:
            lines.append(f"framerate scale factor: {framerate.group(1)}")

        return make_box(subtitle_file.name, lines)
    except subprocess.CalledProcessError as e:
        print(f"Failed: {subtitle_file.name} {e.returncode}")
    except FileNotFoundError:
        print("Failed: ffsubsync not found in PATH.")


def parse_args():
    parser = argparse.ArgumentParser(description="Sync subtitles to a reference audio file using ffsubsync.")
    parser.add_argument("subs_directory", help="Directory containing the subtitles to sync")
    parser.add_argument("--no-framerate", action='store_true',
                    help="Tells ffsubsync to assume the framerate of the subtitle is already correct")
    parser.add_argument("--audio", type=str, default=None,
                    help="Optional audio file to sync to")
    parser.add_argument("--max-workers", type=int, default=None,
                        help="Maximum number of parallel subtitle syncs (default: CPU thread count (max 4))\n"
                             "Note that each additional subtitle processed has diminishing returns for total runtime")
    return parser.parse_args()


def main():
    args = parse_args()

    subs_directory = Path(args.subs_directory).resolve()
    if not subs_directory.exists():
        print(f"Error: Directory not found: {subs_directory}")
        sys.exit(1)
    audio_file = Path(args.audio) if args.audio else find_audio_file(subs_directory.parent)
    if not audio_file.exists():
        print(f"Error: Audio file not found: {audio_file}")
        sys.exit(1)
    
    temp_mkv = audio_file.with_suffix(".mkv")
    audio_file.rename(temp_mkv)
    
    synced_dir = subs_directory / "synced"
    synced_dir.mkdir(exist_ok=True)

    try:
        srt_files = list(subs_directory.glob("*.srt"))
        if not srt_files:
            print(f"No .srt files found in {subs_directory}")
            sys.exit(1)
    
        print(f"Using audio to sync: {audio_file.name}")
        print(f"Found {len(srt_files)} subtitles in {subs_directory}")
        cores = os.cpu_count() or 4
        workers = (
            min(cores // 2, 4)
            if args.max_workers is None
            else args.max_workers
        )
        print(f"Processing in parallel (max workers = {workers})...\n")
        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(process_subtitle, temp_mkv, s, synced_dir, args.no_framerate)
                for s in srt_files
            ]

            for future in as_completed(futures):
                print(future.result())
        end = time.perf_counter()
        print(f"Total time elapsed: {end - start:.3f} seconds")
    finally:
        if temp_mkv.exists():
            temp_mkv.rename(audio_file)
    print("\nAll tasks complete.")


if __name__ == "__main__":
    main()
