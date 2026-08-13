"""
Dependencies:
pip install rich av
ffmpeg https://www.ffmpeg.org/download.html
Ensure ffmpeg is in PATH.

@version 3.1

Video codecs supported: H.264, HEVC, MPEG-2, VC-1
"""
import argparse
import re
import subprocess
import sys
import time
import contextlib

from pathlib import Path
from typing import Any

import av
from rich.console import Console

console = Console(color_system="truecolor")

# --- H.264 ---

def find_idr_frames(video_file: str, target_frame: int, verbose: bool) -> dict[str, Any]:
    """
    Determines whether the target frame is and IDR frame. If not, find the nearest bi-directional IDR frames.
    video_file: Path to the H.264 video file.
    target_frame: Frame number to check.
    """
    start_time = time.time()
    # run ffmpeg trace_headers
    cmd = ['ffmpeg', '-i', str(video_file), '-c', 'copy', '-bsf:v', 'trace_headers', '-f', 'null', '-']
    
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    except FileNotFoundError as fe:
        console.print(f"[red]{video_file} or ffmpeg not found, ensure ffmpeg is in PATH[/]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error running ffmpeg:[/] {e}")
        sys.exit(1)
    
    status_ctx = console.status("Starting scan...", spinner="dots")
    
    idr_frames = set()
    current_frame = -1
    in_slice_header = False
    idr_before = None
    idr_after = None
    target_is_idr = False
    
    # parse h264 bitstream headers
    try:
        with status_ctx as status:
            for line in process.stdout:
                # remove unneeded line content
                match = re.match(r'\[.*?\]\s+(.*)', line)
                if not match:
                    continue
                
                content = match.group(1).strip().lower()
                
                # check for new frame, denoted by access unit delimiter
                if content == "access unit delimiter":
                    current_frame += 1
                    in_slice_header = False
                    
                    if status is not None:
                        status.update(
                            f"Scanning frame {current_frame:,} "
                            f"([cyan]{len(idr_frames)}[/cyan] IDR frame"
                            f"{'s' if len(idr_frames) != 1 else ''} found so far)"
                        )
                    
                    # if we've found an IDR frame after the target, stop
                    if idr_after is not None:
                        process.terminate()
                        break
                    
                    continue
                
                # check for slice header
                if content == "slice header":
                    in_slice_header = True
                    continue
                
                # check if frame is IDR, denoted by slice header having nal_unit_type = 5
                if in_slice_header and "nal_unit_type" in content:
                    parts = content.split('=')
                    if len(parts) >= 2:
                        nal_type = parts[-1].strip()
                        if nal_type == '5':
                            idr_frames.add(current_frame)
                            if target_frame is None:
                                # scanning entire file; don't do target comparisons
                                continue

                            if current_frame == target_frame:
                                # success, target frame as IDR, stop
                                target_is_idr = True
                                process.terminate()
                                break
                            elif current_frame < target_frame:
                                idr_before = current_frame
                            elif current_frame > target_frame and idr_after is None:
                                idr_after = current_frame
    finally:
        process.wait()
    
    end_time = time.time()
    elapsed_time = end_time - start_time
    console.print(f"\nExecution time: [blue]{elapsed_time:.3f}[/] seconds")
    
    frame_data: dict = {
        "safe_frames": idr_frames,
        "safe_before": idr_before,
        "safe_after": idr_after,
        "target_is_safe": bool(target_is_idr),
        "frame_type": "IDR ",
    }
    return frame_data

# --- HEVC ---

# matches the 3-byte start code core. A 4-byte code (00 00 00 01) always
# contains this as a substring starting one byte later, so we detect the
# 4-byte form by checking the byte immediately before the match
_START_CODE_RE = re.compile(rb"\x00\x00\x01")

def get_nal_unit_type_hevc(nalu):
    if len(nalu) < 2:
        return None
    return (nalu[0] >> 1) & 0x3F


def is_first_slice_segment_hevc(nalu):
    if len(nalu) < 3:
        return False
    return (nalu[2] & 0x80) != 0


def iter_nalus_stream_hevc(file_obj, chunk_size=1024 * 1024):
    """
    Yield complete NAL units (without start codes) from an Annex-B
    HEVC bytestream, reading the file incrementally in chunks
    """
    data = b""
    search_from = 0      # don't re-scan bytes we've already searched
    pending_start = None  # byte offset in data where the in-progress NALU begins

    while True:
        chunk = file_obj.read(chunk_size)
        if chunk:
            data += chunk

        # consume every complete start code currently available in the buffer
        while True:
            m = _START_CODE_RE.search(data, search_from)
            if not m:
                break

            code_start = m.start()
            code_len = 3
            if code_start >= 1 and data[code_start - 1] == 0:
                # a 4-byte start code (00 00 00 01).
                code_start -= 1
                code_len = 4

            if pending_start is not None:
                yield data[pending_start:code_start]

            pending_start = code_start + code_len
            search_from = pending_start

        if not chunk:
            # flush whatever NALU was still being accumulated.
            if pending_start is not None:
                yield data[pending_start:]
            break

        # bound memory use, drop bytes we're done with (everything before
        # the NALU currently being accumulated), keeping indices in sync
        if pending_start:
            data = data[pending_start:]
            search_from -= pending_start
            pending_start = 0


def find_idr_frames_hevc(filename: str, target_frame: int, verbose: bool) -> dict[str, Any]:
    target_types = {19, 20}
    frame_num = -1
    idr_frames = []
    idr_before = None
    idr_after = None
    target_is_idr = False
    
    start_time = time.time()
    status_ctx = console.status("Starting scan...", spinner="dots")
    
    with status_ctx as status, open(filename, "rb") as f:
        for nalu in iter_nalus_stream_hevc(f):

            nal_type = get_nal_unit_type_hevc(nalu)
            if nal_type is None or nal_type > 31:
                continue

            if is_first_slice_segment_hevc(nalu):
                frame_num += 1
                if status is not None:
                    status.update(
                        f"Scanning frame {frame_num:,} "
                        f"([cyan]{len(idr_frames)}[/cyan] IDR frame"
                        f"{'s' if len(idr_frames) != 1 else ''} found so far)"
                    )
                if nal_type in target_types:
                    idr_frames.append(frame_num)
                    if target_frame is None:
                        # scanning entire file; don't do target comparisons
                        continue

                    if frame_num == target_frame:
                        # success, target frame as IDR
                        target_is_idr = True
                    elif frame_num < target_frame:
                        idr_before = frame_num
                    elif frame_num > target_frame:
                        idr_after = frame_num
                        break

                if idr_after is not None:
                    break
    
    end_time = time.time()
    elapsed_time = end_time - start_time
    console.print(f"\nExecution time: [blue]{elapsed_time:.3f}[/] seconds")
    
    frame_data: dict = {
        "safe_frames": idr_frames,
        "safe_before": idr_before,
        "safe_after": idr_after,
        "target_is_safe": bool(target_is_idr),
        "frame_type": "IDR ",
    }
    return frame_data

# --- MPEG-2 ---

def find_safe_frames_mpeg2(video_file: str, target_frame: int, verbose: bool) -> dict[str, Any]:
    """
    Determines whether the target frame is a closed GOP I-frame.
    If not, find the nearest bi-directional closed GOP I-frames.
    video_file: Path to the MPEG-2 video file.
    target_frame: Frame number to check.
    """
    start_time = time.time()
    cmd = ['ffmpeg', '-i', str(video_file), '-c', 'copy', '-bsf:v', 'trace_headers', '-f', 'null', '-']
 
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    except FileNotFoundError:
        console.print(f"[red]{video_file} or ffmpeg not found, ensure ffmpeg is in PATH[/]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error running ffmpeg:[/] {e}")
        sys.exit(1)
 
    status_ctx = console.status("Starting scan...", spinner="dots")
 
    safe_cut_frames = set()   # closed GOP I-frames
    all_i_frames = set()      # every I-frame regardless of GOP type
    in_picture_header = False
    in_gop_header = False
    pending_closed_gop = False  # closed_gop flag from the most recent GOP header
    current_temporal_ref = 0    # temporal_reference value of the current picture
    max_temporal_ref = -1       # highest temporal_reference seen in the current GOP
    gop_display_base = 0        # display-order frame number of the first frame in this GOP
    safe_before = None
    safe_after = None
    target_is_safe = False
 
    # NOTE: MPEG-2 frames are stored in decode order but displayed in a different order.
    # B-frames are decoded after the I/P frames they reference, but displayed before them.
    # each picture header carries a temporal_reference field which is the frame's
    # display-order offset within its GOP. The display frame number is:
    #   display_frame = gop_display_base + temporal_reference
 
    try:
        with status_ctx as status:
            for line in process.stdout:
                match = re.match(r'\[.*?\]\s+(.*)', line)
                if not match:
                    continue
 
                content = match.group(1).strip().lower()
 
                # GOP header will tell us if the upcoming I-frame is a closed or open GOP I-frame.
                # advance the display base by the number of frames in the previous GOP
                # (max temporal_reference + 1), then reset for the new GOP.
                if content == "group of pictures header":
                    in_gop_header = True
                    in_picture_header = False
                    gop_display_base += max_temporal_ref + 1
                    max_temporal_ref = -1
                    pending_closed_gop = False  # reset, updated below if field is present
                    continue
 
                if in_gop_header and "closed_gop" in content:
                    parts = content.split('=')
                    if len(parts) >= 2:
                        pending_closed_gop = parts[-1].strip() == '1'
                    in_gop_header = False
                    continue
 
                # new frame, reset temporal ref, check early exit
                if content == "picture header":
                    in_picture_header = True
                    in_gop_header = False
                    current_temporal_ref = 0
 
                    if status is not None:
                        status.update(
                            f"Scanning around display frame {gop_display_base:,} "
                            f"([cyan]{len(safe_cut_frames)}[/cyan] closed GOP I-frame"
                            f"{'s' if len(safe_cut_frames) != 1 else ''} found so far)"
                        )
 
                    if safe_after is not None:
                        process.terminate()
                        break
 
                    continue
 
                # capture the display-order offset of this frame within its GOP
                if in_picture_header and "temporal_reference" in content:
                    parts = content.split('=')
                    if len(parts) >= 2:
                        try:
                            current_temporal_ref = int(parts[-1].strip())
                            if current_temporal_ref > max_temporal_ref:
                                max_temporal_ref = current_temporal_ref
                        except ValueError:
                            pass
                    continue
 
                # frame type, use display_frame for all comparisons
                if in_picture_header and "picture_coding_type" in content:
                    in_picture_header = False
                    parts = content.split('=')
                    if len(parts) >= 2:
                        coding_type = parts[-1].strip()
                        if coding_type == '1':  # I-frame
                            decode_frame = gop_display_base
                            display_frame = gop_display_base + current_temporal_ref
                            all_i_frames.add((decode_frame, display_frame))
                            if pending_closed_gop:
                                safe_cut_frames.add((decode_frame, display_frame))
                                if target_frame is None:
                                    # scanning entire file; don't do target comparisons
                                    continue

                                if display_frame == target_frame:
                                    target_is_safe = True
                                    process.terminate()
                                    break
                                elif display_frame < target_frame:
                                    safe_before = (decode_frame, display_frame)
                                elif display_frame > target_frame and safe_after is None:
                                    safe_after = (decode_frame, display_frame)
    finally:
        process.wait()
 
    end_time = time.time()
    console.print(f"\nExecution time: [blue]{end_time - start_time:.3f}[/] seconds")
    console.print(f"\nMPEG-2 output frame format: (decoding_order, display_order)")
    
    frame_data: dict = {
        "safe_frames": safe_cut_frames,
        "safe_before": safe_before,
        "safe_after": safe_after,
        "target_is_safe": bool(target_is_safe),
        "frame_type": "closed GOP I-",
    }
    return frame_data

# --- VC-1 ---

def find_safe_frames_vc1(video_file: str, target_frame: int, verbose: bool) -> dict[str, Any]:
    """
    Finds closed entry-point I-frames in a VC-1 Advanced Profile elementary stream by
    parsing the raw bitstream.
 
    ffmpeg trace_headers does not support VC-1, so instead we scan the file for
    4-byte start codes (0x00 0x00 0x01 + suffix) manually:
        0x0D = Frame
        0x0E = Entry Point Header
        0x0F = Sequence Header
    (SMPTE 421M Annex E; confirmed by GStreamer VC-1 parser)
 
    In VC-1 AP, an Entry Point Header always immediately precedes the I-frame
    it introduces. A safe cut point is any frame immediately following an
    Entry Point Header where CLOSED_ENTRY = 1, meaning the segment is
    self-contained and does not reference any frames from the previous segment.
 
    Entry point header bit layout (SMPTE 421M §6.2, bits packed MSB-first):
        bit 7 of byte[0] after start code: BROKEN_LINK
        bit 6 of byte[0] after start code: CLOSED_ENTRY
 
    NOTE: Frame numbers reported here are in decode order, which may differ
    from display order if the stream contains B-frames. Unlike MPEG-2, VC-1
    does not carry a temporal_reference field that is easily parsed
    without fully parsing the complex AP frame header syntax.
    The parsing below was derived from the SMPTE Standard VC-1 proposal document
    found here https://multimedia.cx/mirror/s421m.pdf
    """
    start_time = time.time()
 
    # VC-1 AP start code suffixes
    SC_FRAME       = 0x0D
    SC_ENTRYPOINT  = 0x0E
 
    safe_cut_frames = set()        # closed entry-point I-frames
    all_i_frames = set()           # every I-frame (i.e. every frame following any entry point)
    current_frame = -1
    pending_closed_entry = False   # CLOSED_ENTRY from the most recent entry point header
    pending_any_entry = False      # any entry point seen (closed or open), for all_i_frames
    safe_before = None
    safe_after = None
    target_is_safe = False
    done = False
 
    status_ctx = console.status("Starting scan...", spinner="dots")
 
    # read in chunks with a 4-byte tail carried over between chunks so that
    # start codes surrounding a chunk boundary are never missed
    CHUNK_SIZE = 65536
 
    try:
        with open(video_file, 'rb') as f, status_ctx as status:
            tail = b''
            while not done:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
 
                data = tail + chunk
                i = 0
 
                while i <= len(data) - 4:
                    # skip bytes that can't start a start code
                    if data[i] != 0x00:
                        i += 1
                        continue
                    if data[i+1] != 0x00:
                        i += 2
                        continue
                    if data[i+2] != 0x01:
                        i += 1
                        continue
 
                    scs = data[i+3]
 
                    if scs == SC_ENTRYPOINT:
                        # The byte immediately after the start code holds
                        # BROKEN_LINK (bit 7) and CLOSED_ENTRY (bit 6).
                        # This byte can never be an emulation prevention byte
                        # (0x03) because it follows directly after 0x01.
                        if i + 4 < len(data):
                            header_byte = data[i+4]
                            pending_closed_entry = bool(header_byte & 0x40)  # bit 6
                            pending_any_entry = True
                        i += 4
 
                    elif scs == SC_FRAME:
                        current_frame += 1
 
                        if status is not None:
                            status.update(
                                f"Scanning frame {current_frame:,} "
                                f"([cyan]{len(safe_cut_frames)}[/cyan] CEP I-frame"
                                f"{'s' if len(safe_cut_frames) != 1 else ''} found so far)"
                            )
 
                        # every frame that follows any entry point is an I-frame
                        if pending_any_entry:
                            all_i_frames.add(current_frame)
 
                        if pending_closed_entry:
                            safe_cut_frames.add(current_frame)
                            if target_frame is None:
                                # scanning entire file; don't do target comparisons
                                continue

                            if current_frame == target_frame:
                                target_is_safe = True
                                done = True
                                break
                            elif current_frame < target_frame:
                                safe_before = current_frame
                            elif current_frame > target_frame and safe_after is None:
                                safe_after = current_frame
 
                        # consume the entry point flags regardless of type
                        pending_closed_entry = False
                        pending_any_entry = False
 
                        if safe_after is not None:
                            done = True
                            break
 
                        i += 4
 
                    else:
                        i += 4
 
                # carry the last 3 bytes into the next iteration so start codes
                # at chunk boundaries are not missed
                tail = data[-3:]
 
    except FileNotFoundError:
        console.print(f"[red]{video_file} not found[/]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error reading {video_file}:[/] {e}")
        sys.exit(1)
 
    end_time = time.time()
    console.print(f"\nExecution time: [blue]{end_time - start_time:.3f}[/] seconds")
    
    frame_data: dict = {
        "safe_frames": safe_cut_frames,
        "safe_before": safe_before,
        "safe_after": safe_after,
        "target_is_safe": bool(target_is_safe),
        "frame_type": "CEP I-",
    }
    return frame_data


def main():
    parser = argparse.ArgumentParser(
        description='Check if a frame is an IDR frame in an H.264/HEVC stream, a closed GOP I-frame in an MPEG-2 stream, or a closed entry-point I-frame in a VC-1 stream.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
            Usage:
            check_idr.py video.h264 --frame 1000
            check_idr.py video.m2v -f 1000 --verbose
            check_idr.py video.vc1 -f 1000 -v
            check_idr.py video.hevc
        '''
    )
    parser.add_argument('video_file', help='Path to the raw stream video file')
    parser.add_argument('-f', '--frame', type=int, default=None,
                        help='Frame number to check (omit to scan the entire file)')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='console.prints a list of all IDR/closed GOP/closed entry-point frames from 0 -> --frame')
    
    args = parser.parse_args()
    
    video_file = Path(args.video_file)
    av_file = av.open(Path(video_file))
    stream_type = av_file.format.name
    stream = av_file.streams[0]
    profile = stream.codec_context.profile
    if stream_type not in ("h264", "mpegvideo", "vc1", "hevc"):
        console.print(f"[yellow]Video file must be a raw h264, hevc, mpeg, or vc1 stream.[/yellow]")
        console.print(f"[yellow]Detected file format:[/yellow] {stream_type}")
        return

    console.print(f"[green]{video_file.name} detected as:[/] {stream_type} {profile}")
        
    try:
        frame = int(args.frame) if args.frame else None
    except ValueError as ve:
        console.print(f"[red]Frame number must be an integer[/]")
        sys.exit(1)

    verbose = args.verbose

    if frame and frame < 0:
        console.print("[red]Frame number must be non-negative[/]")
        sys.exit(1)

    frame_data: dict = None
    if stream_type == "h264":
        frame_data = find_idr_frames(str(video_file), frame, verbose)
    elif stream_type == "hevc":
        frame_data = find_idr_frames_hevc(str(video_file), frame, verbose)
    elif stream_type == "mpegvideo":
        frame_data = find_safe_frames_mpeg2(str(video_file), frame, verbose)
    elif stream_type == "vc1":
        if profile != "Advanced":
            console.print(f"{profile} [yellow]format profile VC-1 streams are not supported[/]")
            return
        console.print("[b]Note that frame numbers outputted for VC-1 streams are in [i]decoded[/i] order, " +
                      "which may not match the [i]display[/i] order.[/b]")
        frame_data = find_safe_frames_vc1(str(video_file), frame, verbose)
    
    frame_type = frame_data["frame_type"]
    safe_frames = frame_data["safe_frames"]
    safe_before = frame_data["safe_before"]
    safe_after = frame_data["safe_after"]
    if frame is not None:
        if frame_data["target_is_safe"]:
            console.print(f"[green]Frame {frame} is {frame_type.strip()}[/]")
        else:
            console.print(f"[yellow]Frame {frame} is NOT {frame_type.strip()}[/]")
        
        if safe_before is not None:
            console.print(f"Nearest {frame_type}frame before target: [green]{safe_before}[/]")
        else:
            console.print(f"No {frame_type}frame found before the target frame")
        
        if safe_after is not None:
            console.print(f"Nearest {frame_type}frame after target: [green]{safe_after}[/]")
        else:
            console.print(f"No {frame_type}frame found after the target frame")
    else:
        console.print(f"[green]Found {len(safe_frames)} {frame_type}frames[/]")

    if verbose or frame is None:
        console.print(f"All {frame_type}frames found: [green]{sorted(safe_frames)}[/]")

if __name__ == "__main__":
    main()
