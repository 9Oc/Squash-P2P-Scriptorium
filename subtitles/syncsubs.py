"""
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
import re
import sys
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

ALPHABETICAL_CODE_MAP = {
    "en-US": "american.en-US",
    "en-AU": "australian.en-AU",
    "en-GB": "british.en-GB",
    "en-CA": "canadian.en-CA",
    "sq": "albanian.sq",
    "bs": "bosnian.bs",
    "bg": "bulgarian.bg",
    "zh-Hans": "chinese.zh-Hans",
    "zh-Hant": "chinese.zh-Hant",
    "yue-Hant": "cantonese.yue-Hant",
    "es-ES": "spain.es-ES",
    "es-419": "spanish.es-419",
    "nl": "dutch.nl",
    "nl-BE": "dutch.nl-BE",
    "ka": "georgian.ka",
    "de": "german.de",
    "el": "greek.el",
    "hr": "croatian.hr",
    "is": "ice",
    "ky": "kirghiz.ky",
    "lv": "latvian.lv",
    "fa": "persian.fa",
    "pt-PT": "portuguese.pt-PT",
    "sr": "serbian.sr",
    "tl": "tagalog.tl",
}
ALPHABETICAL_CODE_MAP_LOWER = {k.lower(): v for k, v in ALPHABETICAL_CODE_MAP.items()}

AUDIO_EXTENSIONS = [
    ".ac3", ".ec3", ".eac3", ".aac", ".flac", ".wav",
    ".thd", ".dts", ".dtshd", ".dtsma", ".opus"
]

PROGRESS_PATTERN = re.compile(r"^\s*\d{1,3}%\|.*$")


def get_alphabetical_lang_code(lang_code: str) -> str:
    if not lang_code:
        return lang_code
    base_code = lang_code.split("[")[0]  # remove [sdh] or [cc] for mapping
    mapped = ALPHABETICAL_CODE_MAP_LOWER.get(base_code.lower(), base_code)
    # re-append [sdh] or [cc] if present
    if "[" in lang_code:
        mapped += lang_code[lang_code.index("["):]
    return mapped
    

def find_audio_file(directory: Path, specified: Path = None) -> Path:
    for ext in AUDIO_EXTENSIONS:
        files = list(directory.glob(f"*{ext}"))
        if files:
            return files[0].resolve()
    
    print(f"No audio file found in {directory} with extensions: {AUDIO_EXTENSIONS}")
    sys.exit(1)


def process_subtitle(mkv_file: Path, subtitle_file: Path, output_dir: Path):
    """Sync one subtitle file using ffsubsync."""
    filename = subtitle_file.stem
    parts = filename.split('.')
    lang_code = parts[-1] if len(parts) > 1 else None
    if not lang_code:
        output_file = output_dir / f"{filename}.srt"
    else:
        new_file_name = filename.rsplit('.', 1)[0]
        new_file_name = re.sub(r"\.+", ".", new_file_name).strip(".")
        alphabetical_lang_code = get_alphabetical_lang_code(lang_code)
        ENGLISH_CODES = {"en", "american.en-US", "australian.en-AU", "british.en-GB", "canadian.en-CA"}
        if alphabetical_lang_code in ENGLISH_CODES:
            alphabetical_lang_code = "_" + alphabetical_lang_code
        output_file = output_dir / f"{new_file_name}.{alphabetical_lang_code}.srt"
    

    cmd = [
        "ffs",
        str(mkv_file),
        "-i", str(subtitle_file),
        "-o", str(output_file)
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        log = result.stdout.splitlines() + result.stderr.splitlines()
        filtered_lines = [line for line in log if not PROGRESS_PATTERN.match(line)]
        header = f"\n=== {subtitle_file.name} → {output_file.name} ===\n"
        return header + "\n".join(filtered_lines)
    except subprocess.CalledProcessError as e:
        print(f"Failed: {subtitle_file.name} {e.returncode}")
    except FileNotFoundError:
        print("Error: ffsubsync not found in PATH.")


def parse_args():
    parser = argparse.ArgumentParser(description="Sync subtitles to a reference audio file using ffsubsync.")
    parser.add_argument("subs_directory", help="Directory containing the subtitles to sync")
    parser.add_argument("--audio", type=str, default=None,
                    help="Optional audio file to sync to")
    parser.add_argument("--max-workers", type=int, default=None,
                        help="Maximum number of parallel subtitle syncs (default: CPU count)")
    return parser.parse_args()


def main():
    args = parse_args()

    subs_directory = Path(args.subs_directory).resolve()
    if not subs_directory.exists():
        print(f"Error: Directory not found: {subs_directory}")
        sys.exit(1)
    if not args.audio:
        audio_file = find_audio_file(subs_directory.parent)
    else:
        audio_file = Path(args.audio)
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
        print(f"Processing in parallel (max workers = {args.max_workers or 'auto'})...\n")
        futures = []
        with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
            for s in srt_files:
                futures.append(executor.submit(process_subtitle, temp_mkv, s, synced_dir))
                
            for future in as_completed(futures):
                output = future.result()
                print(output)
    finally:
        if temp_mkv.exists():
            temp_mkv.rename(audio_file)
    print("\nAll tasks complete.")


if __name__ == "__main__":
    main()
