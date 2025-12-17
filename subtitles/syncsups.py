"""
Dependencies:
    pip install ffsubsync
    pip install git+https://github.com/cubicibo/SUPer.git
    ffmpeg must be in your PATH.
"""
import argparse
import re
import shutil
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta
from pathlib import Path

from SUPer import SUPFile, PCS, ENDS, PDS, ODS
from SUPer.utils import BDVideo

AUDIO_EXTENSIONS = [
    ".ac3", ".ec3", ".eac3", ".aac", ".flac", ".wav", ".mlp",
    ".thd", ".dts", ".dtshd", ".dtshr", ".dtsma", ".opus"
]

# filter ffsubsync progress/tqdm lines
PROGRESS_RE = re.compile(
    r"^\s*\d{1,3}%\|.*$"          # progress bar lines
    r"|^\s*\d+(\.\d+)?it.*$"      # tqdm iteration lines like '100.0it [00:00, 160.46it/s]'
)

# srt timestamp regex
SRT_TS_RE = re.compile(r"^\s*(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\s*$")


def td_to_srt(td: timedelta) -> str:
    # convert timedelta to srt timestamp
    total_ms = int(td.total_seconds() * 1000)
    h = total_ms // 3600000
    m = (total_ms % 3600000) // 60000
    s = (total_ms % 60000) // 1000
    ms = total_ms % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def srt_to_td(srt_ts: str) -> timedelta:
    # convert srt timestamp to timedelta
    h, m, rest = srt_ts.split(":")
    s, ms = rest.split(",")
    total_ms = (int(h) * 3600 + int(m) * 60 + int(s)) * 1000 + int(ms)
    return timedelta(milliseconds=total_ms)
    

def find_audio_file(directory: Path) -> Path:
    # find the first audio file in the given directory
    for ext in AUDIO_EXTENSIONS:
        files = list(directory.glob(f"*{ext}"))
        if files:
            return files[0].resolve()
    
    print(f"No audio file found in {directory} with extensions: {AUDIO_EXTENSIONS}")
    sys.exit(1)


def map_to_nearest_fps(calculated_fps, fps_lut):
    """Map a calculated FPS value to the nearest standard FPS in the lookup table."""
    return min(fps_lut.keys(), key=lambda x: abs(x - calculated_fps))


def extract_sup_events(sup: SUPFile) -> list[tuple[timedelta, timedelta]]:
    # flatten displaysets and segments
    display_sets = [ds for epoch in sup.epochs() for ds in epoch]
    seg_records = []
    for ds_index, ds in enumerate(display_sets):
        for seg_index, seg in enumerate(ds):
            seg_records.append((seg, ds_index, seg_index))

    def pts_of(seg):
        v = getattr(seg, "pts", None)
        return float(v) if v is not None else None

    def first_pts_in_ds(ds):
        for seg in ds:
            v = getattr(seg, "pts", None)
            if v is not None:
                return float(v)
        return None

    # collect pcs and ends indices and image segment indices
    pcs_indices = []
    ends_indices = []
    image_indices = set()
    for idx, (seg, ds_i, s_i) in enumerate(seg_records):
        if isinstance(seg, PCS):
            pcs_indices.append(idx)
        if isinstance(seg, ENDS):
            ends_indices.append(idx)
        if isinstance(seg, (PDS, ODS)):
            image_indices.add(idx)

    events = []

    for i, pcs_idx in enumerate(pcs_indices):
        pcs_seg, pcs_ds_i, pcs_s_i = seg_records[pcs_idx]
        start_pts = pts_of(pcs_seg)
        if start_pts is None:
            start_pts = first_pts_in_ds(display_sets[pcs_ds_i]) or 0.0

        # find next PCS record index (if any) and its pts
        next_pcs_idx = pcs_indices[i+1] if i+1 < len(pcs_indices) else None
        next_pcs_pts = None
        if next_pcs_idx is not None:
            next_pcs_seg = seg_records[next_pcs_idx][0]
            next_pcs_pts = pts_of(next_pcs_seg) or first_pts_in_ds(display_sets[seg_records[next_pcs_idx][1]])

        # find ENDS between pcs_idx and next_pcs_idx (exclusive)
        chosen_end_idx = None
        candidate_end_pts = None
        # search ENDS in the window (pcs_idx, next_pcs_idx)
        for e_idx in reversed(ends_indices):
            if e_idx <= pcs_idx:
                break
            if next_pcs_idx is not None and e_idx >= next_pcs_idx:
                continue
            # e_idx is after PCS and before next PCS (or next_pcs_idx is None)
            e_seg, e_ds_i, e_s_i = seg_records[e_idx]
            e_pts = pts_of(e_seg)
            if e_pts is None:
                # fallback to last pts in that DS
                for seg in reversed(display_sets[e_ds_i]):
                    v = getattr(seg, "pts", None)
                    if v is not None:
                        e_pts = float(v)
                        break
            # prefer ENDS whose pts >= start_pts
            if e_pts is not None and e_pts >= start_pts:
                chosen_end_idx = e_idx
                candidate_end_pts = e_pts
                break
            # otherwise remember the last ENDS (even if < start); keep searching for better
            if chosen_end_idx is None:
                chosen_end_idx = e_idx
                candidate_end_pts = e_pts

        # if chosen_end_pts exists but is < start_pts, prefer next PCS.pts if available
        final_end_pts = None
        if candidate_end_pts is not None and candidate_end_pts >= start_pts:
            final_end_pts = candidate_end_pts
        else:
            # prefer next PCS.pts to end this visual if available
            if next_pcs_pts is not None:
                final_end_pts = next_pcs_pts
            else:
                # fallback: first ENDS after pcs_idx
                for e_idx in ends_indices:
                    if e_idx > pcs_idx:
                        e_seg, e_ds_i, e_s_i = seg_records[e_idx]
                        e_pts2 = pts_of(e_seg)
                        if e_pts2 is None:
                            for seg in reversed(display_sets[e_ds_i]):
                                v = getattr(seg, "pts", None)
                                if v is not None:
                                    e_pts2 = float(v)
                                    break
                        if e_pts2 is not None:
                            final_end_pts = e_pts2
                            break

        # final fallback: any later seg pts
        if final_end_pts is None:
            for j in range(pcs_idx, len(seg_records)):
                v = getattr(seg_records[j][0], "pts", None)
                if v is not None:
                    final_end_pts = float(v)
                    break

        if final_end_pts is None:
            # give up
            continue

        # ensure there's at least one image between pcs_idx and the chosen end record
        # determine end search index (if we used chosen_end_idx use that, else use next_pcs_idx or first ENDS after)
        if chosen_end_idx is not None:
            search_end_idx = chosen_end_idx
        elif next_pcs_idx is not None:
            search_end_idx = next_pcs_idx - 1
        else:
            # find first ends after pcs_idx
            se = None
            for e_idx in ends_indices:
                if e_idx > pcs_idx:
                    se = e_idx
                    break
            search_end_idx = se if se is not None else len(seg_records) - 1

        has_image = False
        for j in range(pcs_idx, min(search_end_idx + 1, len(seg_records))):
            if j in image_indices:
                has_image = True
                break

        if not has_image:
            # control-only PCS -> WDS -> ENDS; skip
            continue

        events.append((timedelta(seconds=float(start_pts)), timedelta(seconds=float(final_end_pts))))

    return events


def write_dummy_srt(events, out_path: Path):
    with open(out_path, "w", encoding="utf-8") as f:
        for i, (s_td, e_td) in enumerate(events, start=1):
            f.write(f"{i}\n{td_to_srt(s_td)} --> {td_to_srt(e_td)}\nDUMMY\n\n")


def run_ffsubsync(mkv_file: Path, srt_in: Path, srt_out: Path):
    cmd = ["ffs", str(mkv_file), "-i", str(srt_in), "-o", str(srt_out)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    lines = (result.stdout or "").splitlines() + (result.stderr or "").splitlines()
    filtered_log = "\n".join([ln for ln in lines if not PROGRESS_RE.match(ln)])

    if result.returncode != 0:
        raise RuntimeError(f"ffsubsync failed (exit {result.returncode})\n{filtered_log}")
    if not srt_out.exists():
        raise RuntimeError(f"ffsubsync did not produce output file: {srt_out}\n{filtered_log}")

    return filtered_log


def parse_framerate_factor(log: str) -> float | None:
    # parse the framerate factor from the ffsubsync log
    m = re.search(r"framerate scale factor:\s*([0-9.]+)", log)
    if m:
        factor = float(m.group(1))
        if factor == 1.043:
            factor = 1.0427
        elif factor == 1.042:
            factor = 1.04166
        return factor
    return None


def get_srt_events(srt_path: str | Path) -> list[tuple[timedelta, timedelta]]:
    # returns a list of tuples containing the start and end timestamps
    # in timedelta format from the given srt file
    srt_path = Path(srt_path)
    events = []
    with open(srt_path, "r", encoding="utf-8") as f:
        for line in f:
            m = SRT_TS_RE.match(line)
            if m:
                s_td = srt_to_td(m.group(1))
                e_td = srt_to_td(m.group(2))
                events.append((s_td, e_td))
    return events


def describe_seg(seg):
    info = {
        "type": type(seg).__name__,
    }
    # common timing fields (if present)
    for tattr in ("pts", "dts"):
        if hasattr(seg, tattr):
            info[tattr] = getattr(seg, tattr)
    # FPS if present
    if hasattr(seg, "fps"):
        info["fps"] = getattr(seg, "fps")
    # if segment exposes text
    if hasattr(seg, "text"):
        txt = getattr(seg, "text")
        info["text"] = txt if txt is not None else ""
    # payload/byte length for binary segments (images, palettes)
    try:
        b = bytes(seg)
        info["bytes_len"] = len(b)
    except Exception:
        info["bytes_len"] = None
    return info


def write_synced_sup(original_sup, out_path, synced_events: list[tuple[timedelta, timedelta]], new_fps_val=None):
    # flatten displaysets and build seg_records
    display_sets = [ds for epoch in original_sup.epochs() for ds in epoch]
    seg_records = []
    for ds_index, ds in enumerate(display_sets):
        for seg_index, seg in enumerate(ds):
            seg_records.append((seg, ds_index, seg_index))

    def pts_of(seg):
        v = getattr(seg, "pts", None)
        return float(v) if v is not None else None

    def first_pts_in_ds(ds):
        for seg in ds:
            v = getattr(seg, "pts", None)
            if v is not None:
                return float(v)
        return None

    # collect indices
    pcs_indices = []
    ends_indices = []
    image_indices = set()
    for idx, (seg, ds_i, s_i) in enumerate(seg_records):
        if isinstance(seg, PCS):
            pcs_indices.append(idx)
        if isinstance(seg, ENDS):
            ends_indices.append(idx)
        if isinstance(seg, (PDS, ODS)):
            image_indices.add(idx)

    # build mapping: for each pcs_idx that yields an event, determine chosen_end_idx (or next PCS)
    mapping = []  # list of tuples (pcs_idx, chosen_end_idx_or_None, chosen_end_is_next_pcs_bool)
    for i, pcs_idx in enumerate(pcs_indices):
        pcs_seg, pcs_ds_i, pcs_s_i = seg_records[pcs_idx]
        start_pts = pts_of(pcs_seg)
        if start_pts is None:
            start_pts = first_pts_in_ds(display_sets[pcs_ds_i]) or 0.0

        next_pcs_idx = pcs_indices[i+1] if i+1 < len(pcs_indices) else None
        next_pcs_pts = None
        if next_pcs_idx is not None:
            next_pcs_seg = seg_records[next_pcs_idx][0]
            next_pcs_pts = pts_of(next_pcs_seg) or first_pts_in_ds(display_sets[seg_records[next_pcs_idx][1]])

        # choose ENDS in window (pcs_idx, next_pcs_idx)
        chosen_end_idx = None
        candidate_end_pts = None
        for e_idx in reversed(ends_indices):
            if e_idx <= pcs_idx:
                break
            if next_pcs_idx is not None and e_idx >= next_pcs_idx:
                continue
            e_seg, e_ds_i, e_s_i = seg_records[e_idx]
            e_pts = pts_of(e_seg)
            if e_pts is None:
                for seg in reversed(display_sets[e_ds_i]):
                    v = getattr(seg, "pts", None)
                    if v is not None:
                        e_pts = float(v)
                        break
            if e_pts is not None and e_pts >= start_pts:
                chosen_end_idx = e_idx
                candidate_end_pts = e_pts
                break
            if chosen_end_idx is None:
                chosen_end_idx = e_idx
                candidate_end_pts = e_pts

        # determine final_end decision (same logic as extractor)
        final_end_pts = None
        end_is_next_pcs = False
        if candidate_end_pts is not None and candidate_end_pts >= start_pts:
            final_end_pts = candidate_end_pts
        else:
            if next_pcs_pts is not None:
                final_end_pts = next_pcs_pts
                end_is_next_pcs = True
            else:
                for e_idx in ends_indices:
                    if e_idx > pcs_idx:
                        e_seg, e_ds_i, e_s_i = seg_records[e_idx]
                        e_pts2 = pts_of(e_seg)
                        if e_pts2 is None:
                            for seg in reversed(display_sets[e_ds_i]):
                                v = getattr(seg, "pts", None)
                                if v is not None:
                                    e_pts2 = float(v)
                                    break
                        if e_pts2 is not None:
                            final_end_pts = e_pts2
                            chosen_end_idx = e_idx
                            break

        # fallback: any later seg pts
        if final_end_pts is None:
            for j in range(pcs_idx, len(seg_records)):
                v = getattr(seg_records[j][0], "pts", None)
                if v is not None:
                    final_end_pts = float(v)
                    break

        if final_end_pts is None:
            # no usable end found; skip this PCS
            continue

        # check has_image between pcs_idx and chosen_end (same search_end logic)
        if chosen_end_idx is not None:
            search_end_idx = chosen_end_idx
        elif next_pcs_idx is not None:
            search_end_idx = next_pcs_idx - 1
        else:
            se = None
            for e_idx in ends_indices:
                if e_idx > pcs_idx:
                    se = e_idx
                    break
            search_end_idx = se if se is not None else len(seg_records) - 1

        has_image = False
        for j in range(pcs_idx, min(search_end_idx + 1, len(seg_records))):
            if j in image_indices:
                has_image = True
                break
        if not has_image:
            continue

        mapping.append((pcs_idx, chosen_end_idx, end_is_next_pcs))

    # mapping length should match synced_events length or be >=, map up to min
    count = min(len(mapping), len(synced_events))

    # apply synced_events to the exact segments chosen:
    for ev_i in range(count):
        pcs_idx, chosen_end_idx, end_is_next_pcs = mapping[ev_i]
        start_td, end_td = synced_events[ev_i]
        s_sec = start_td.total_seconds()
        e_sec = end_td.total_seconds()

        # update PCS start segment (the PCS object at pcs_idx)
        pcs_seg, pcs_ds_i, pcs_s_i = seg_records[pcs_idx]
        # prefer setting the PCS segment pts/dts; if it's missing pts attribute fall back to DS first seg
        if hasattr(pcs_seg, "pts"):
            pcs_seg.pts = s_sec
        if hasattr(pcs_seg, "dts"):
            pcs_seg.dts = s_sec
        if hasattr(pcs_seg, "update") and callable(pcs_seg.update):
            pcs_seg.update()

        # update chosen end target:
        if end_is_next_pcs and pcs_indices and (pcs_idx in pcs_indices):
            # end chosen is the next PCS, find that PCS segment obj and set its pts/dts
            # locate next PCS index in pcs_indices sequence
            pos = None
            try:
                pos = pcs_indices.index(pcs_idx)
            except ValueError:
                pos = None
            if pos is not None and pos + 1 < len(pcs_indices):
                next_pcs_record_idx = pcs_indices[pos + 1]
                next_pcs_seg, next_pcs_ds_i, next_pcs_s_i = seg_records[next_pcs_record_idx]
                if hasattr(next_pcs_seg, "pts"):
                    next_pcs_seg.pts = e_sec
                if hasattr(next_pcs_seg, "dts"):
                    next_pcs_seg.dts = e_sec
                if hasattr(next_pcs_seg, "update") and callable(next_pcs_seg.update):
                    next_pcs_seg.update()
        elif chosen_end_idx is not None:
            end_seg, end_ds_i, end_s_i = seg_records[chosen_end_idx]
            if hasattr(end_seg, "pts"):
                end_seg.pts = e_sec
            if hasattr(end_seg, "dts"):
                end_seg.dts = e_sec
            if hasattr(end_seg, "update") and callable(end_seg.update):
                end_seg.update()
        else:
            # fallback: try to set the last segment in the PCS's DS to end time
            ds = display_sets[pcs_ds_i]
            for seg in reversed(ds):
                if hasattr(seg, "pts"):
                    seg.pts = e_sec
                    if hasattr(seg, "dts"):
                        seg.dts = e_sec
                    if hasattr(seg, "update") and callable(seg.update):
                        seg.update()
                    break

    # one-time FPS patch if requested (preserve previous behavior)
    fps_updated = getattr(original_sup, "_fps_updated", False)
    if new_fps_val is not None:
        for ds in display_sets:
            for seg in ds:
                if isinstance(seg, PCS) and not fps_updated:
                    if hasattr(seg, "fps"):
                        seg.fps = new_fps_val
                    original_sup._fps_updated = True
                    fps_updated = True
                    if hasattr(seg, "update") and callable(seg.update):
                        seg.update()
                    break
            if fps_updated:
                break

    # write all segments in original order
    with out_path.open("wb") as fp:
        for ds in display_sets:
            for seg in ds:
                if hasattr(seg, "update") and callable(seg.update):
                    try:
                        seg.update()
                    except Exception:
                        pass
                fp.write(bytes(seg))

    return {"mapped": count, "mapping_len": len(mapping), "synced_count": len(synced_events)}


def process_sup(mkv_file: Path, sup_in: Path, dirs):
    dummy_dir, synced_dir, final_dir = dirs
    dummy_srt = dummy_dir / (sup_in.stem + ".srt")
    synced_srt = synced_dir / (sup_in.stem + ".synced.srt")
    sup_out = final_dir / (sup_in.stem + ".synced.sup")

    sup = SUPFile(sup_in)
    events = extract_sup_events(sup)
    print(f"{sup_in.stem}, image events: {len(events)}")
    if not events:
        return f"SKIP (no epochs): {sup_in.name}"

    write_dummy_srt(events, dummy_srt)

    try:
        log = run_ffsubsync(mkv_file, dummy_srt, synced_srt)
    except Exception as e:
        return f"FAILED (ffsubsync): {sup_in.name}\n{e}"

    factor = parse_framerate_factor(log)

    synced_events = get_srt_events(synced_srt)
    if not synced_events:
        return f"FAILED (no synced events): {sup_in.name}\n{log}"
    
    if len(synced_events) != len(events):
        synced_events = synced_events[:min(len(synced_events), len(events))]
    new_fps_val = BDVideo.to_pcsfps(sup.get_fps())
    try:
        if factor is not None and factor != 1.0:
            current_fps_val = float(sup.get_fps().value)
            new_fps_val = current_fps_val / factor
            closest_fps = map_to_nearest_fps(new_fps_val, BDVideo._LUT_PCS_FPS)
            new_fps_val = BDVideo._LUT_PCS_FPS[closest_fps]
        write_synced_sup(sup, sup_out, synced_events, new_fps_val)
    except Exception as e:
        return f"FAILED (write_sup): {sup_in.name}\n{e}"

    return f"\nSynced: {sup_in.name} -> {sup_out.name}\n{log}\nOld FPS: {sup.get_fps().value}\nAdjusted FPS: {new_fps_val}\nFPS factor: {factor}"


def main():
    parser = argparse.ArgumentParser(description="Sync .sup PGS subtitles using SUPer epochs + ffsubsync")
    parser.add_argument("sups_directory", help="Directory containing .sup files to be synced")
    parser.add_argument("--audio", type=str, default=None,
                    help="Optional audio file to sync to")
    parser.add_argument("--max-workers", type=int, default=None, help="Max parallel workers")
    parser.add_argument("--keep-temp", action="store_true", help="Keep temporary files after syncing")
    args = parser.parse_args()

    sups_directory = Path(args.sups_directory).resolve()
    sup_files = list(sups_directory.glob("*.sup"))
    if not sup_files:
        print(f"No .sup files found in: {sups_directory}")
        sys.exit(1)
    
    if args.audio:
        audio_file = Path(args.audio)
    else:
        audio_file = find_audio_file(sups_directory.parent)
    if not audio_file or not audio_file.exists():
        print(f"Audio file not found: {audio_file}")
        sys.exit(1)
    
    temp_mkv = audio_file.with_suffix(".mkv")

    dummy_dir = sups_directory / "dummy_srt"
    synced_dummy_dir = sups_directory / "synced_srt"
    synced_sups_dir = sups_directory / "synced_sups"
    for d in (dummy_dir, synced_dummy_dir, synced_sups_dir):
        d.mkdir(exist_ok=True)

    print(f"Syncing to: {audio_file.name}")
    print(f"Found {len(sup_files)} SUP files")

    audio_file.rename(temp_mkv)
    try:
        futures = []
        with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
            for sup_in in sup_files:
                futures.append(executor.submit(process_sup, temp_mkv, sup_in, (dummy_dir, synced_dummy_dir, synced_sups_dir)))
    
            for fut in as_completed(futures):
                try:
                    result = fut.result()
                    print(result)
                except Exception as e:
                    print(f"FAILED: {e}")
    finally:
        if not args.keep_temp:
            shutil.rmtree(dummy_dir, ignore_errors=True)
            shutil.rmtree(synced_dummy_dir, ignore_errors=True)
        if temp_mkv.exists():
            temp_mkv.rename(audio_file)
    
    print("\nAll tasks complete.")


if __name__ == "__main__":
    main()
