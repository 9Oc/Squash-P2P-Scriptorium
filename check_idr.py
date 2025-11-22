"""
Dependencies:
pip install rich
ffmpeg https://www.ffmpeg.org/download.html
Ensure ffmpeg is in PATH.
"""
import subprocess
import sys
import re
import argparse

from rich import print

def find_idr_frames(video_file, target_frame, verbose: bool):
    """
    Find if the target frame is IDR. If not, find the nearest bi-directional IDR frames.
    video_file: Path to the H.264 video file
    target_frame: Frame number to check
    """
    # run ffmpeg trace_headers
    cmd = ['ffmpeg', '-i', str(video_file), '-c', 'copy', '-bsf:v', 'trace_headers', '-f', 'null', '-']
    
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    except FileNotFoundError as fe:
        print(f"[red]{video_file} or ffmpeg not found, ensure ffmpeg is in PATH[/red]")
        sys.exit(1)
    except Exception as e:
        print(f"[red]Error running ffmpeg:[/red] {e}")
        sys.exit(1)
    
    idr_frames = set()
    current_frame = -1
    in_slice_header = False
    idr_before = None
    idr_after = None
    target_is_idr = False
    
    # parse h264 bitstream headers
    try:
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
                        if current_frame == target_frame:
                            # success, target frame as IDR, stop
                            target_is_idr = True
                            idr_frames.add(current_frame)
                            process.terminate()
                            break
                        elif current_frame < target_frame:
                            idr_before = current_frame
                            idr_frames.add(current_frame)
                        elif current_frame > target_frame and idr_after is None:
                            idr_after = current_frame
                            idr_frames.add(current_frame)
    finally:
        process.wait()
    
    if target_is_idr:
        print(f"[green]Frame {target_frame} is an IDR frame[/green]")
        return
    
    print(f"[yellow]Frame {target_frame} is NOT an IDR frame[/yellow]")
    if idr_before is not None:
        print(f"Nearest IDR frame before: [green]{idr_before}[/green]")
    else:
        print("No IDR frame found before the target frame.")
    
    if idr_after is not None:
        print(f"Nearest IDR frame after: [green]{idr_after}[/green]")
    else:
        print("No IDR frame found after the target frame.")
        
    if verbose:
        print(f"All IDR frames found: [green]{sorted(idr_frames)}[/green]")

def main():
    parser = argparse.ArgumentParser(
        description='Check if a frame is an IDR frame in an H.264 video file.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
            Usage:
            check_idr.py video.h264 --frame 1000
            check_idr.py video.h264 -f 1000 --verbose
        '''
    )
    parser.add_argument('video_file', help='Path to the H.264 video file')
    parser.add_argument('-f', '--frame', type=int, required=True,
                        help='Frame number to check')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Prints a list of all IDR frames from 0 -> --frame')
    
    args = parser.parse_args()
    
    video_file = args.video_file
    if not video_file.endswith(".h264") or video_file.endswith(".avc"):
        print(f"[yellow]Video file must be a raw h264 stream, h264 file headers may not be detected for:[/yellow] {video_file}")
        
    try:
        frame = int(args.frame)
    except ValueError as ve:
        print(f"[red]Frame number must be an integer[/red]\n{ve}")
        sys.exit(1)
    verbose = args.verbose
    
    if frame < 0:
        print("[red]Frame number must be non-negative[/red]")
        sys.exit(1)
    
    find_idr_frames(video_file, frame, verbose)

if __name__ == "__main__":
    main()