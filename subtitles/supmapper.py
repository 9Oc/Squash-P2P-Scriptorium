"""
supmapper.py
@author squash

Tonemap .sup files using a reference .sup file for brightness matching.
Optionally provide a relative percentage or RGB value to tonemap without a reference.
All .sup files in the given directory will be tonemapped to the given reference/percentage/RGB value.

Dependencies:
pip install git+https://github.com/cubicibo/SUPer.git
SupMover https://github.com/MonoS/SupMover

SupMover must be added to your PATH with the .exe named "SupMover.exe".
"""
import subprocess
import argparse

from pathlib import Path
from SUPer import SUPFile, PDS

class PGSFile:
    def __init__(self, path, max_rgb):
        self.path = path
        self.max_rgb = max_rgb
        
    def __repr__(self):
        return f"{self.path.stem}"

# YCbCr -> RGB BT.601
def ycbcr_to_rgb(y, cb, cr):
    r = y + 1.402 * (cr - 128)
    g = y - 0.344136 * (cb - 128) - 0.714136 * (cr - 128)
    b = y + 1.772 * (cb - 128)
    r = int(round(max(0, min(255, r))))
    g = int(round(max(0, min(255, g))))
    b = int(round(max(0, min(255, b))))
    return (r, g, b)

# YCbCr -> RGB BT.709 / BT.2020
def ycbcr_to_rgb_limited(y, cb, cr):
    y = (y - 16) * (255 / 219)
    cb = cb - 128
    cr = cr - 128
    r = y + 1.402 * cr
    g = y - 0.344136 * cb - 0.714136 * cr
    b = y + 1.772 * cb
    return tuple(int(round(max(0, min(255, v)))) for v in (r, g, b))

def find_max_rgb_in_sup(sup_path: str | Path) -> int:
    sup_path = Path(sup_path)
    sup = SUPFile(sup_path)
    
    global_max = 0
    
    for ds in sup.displaysets():
        for seg in ds:
            if isinstance(seg, PDS):
                palette = seg.to_palette()
                for pid, entry in palette.palette.items():
                    # entry is a PaletteEntry with y, cr, cb, alpha attributes
                    if entry.alpha > 0:  # check visible pixels only
                        # convert YCbCr to RGB
                        r, g, b = ycbcr_to_rgb_limited(entry.y, entry.cb, entry.cr)
                        current_max = max(r, g, b)
                        if current_max > global_max:
                            global_max = current_max
    
    return global_max
    
def tonemap(pgs: PGSFile, target_percent: float) -> Path:
    """
    Apply the specified tonemap percent the specified PGSFile.
    """
    user_factor = target_percent / 100
    tonemapped_file = pgs.path.parent / "Tonemapped_Subtitles" / f"{pgs.path.stem}_tonemapped.sup"
    print(f"  Applying tonemap: {target_percent:.2f}% ({pgs.path.name})")
    subprocess.run(["SupMover", str(pgs.path), str(tonemapped_file), "--tonemap", str(user_factor)], check=True)
    return tonemapped_file

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Tonemap PGS subtitles (.sup files) to match reference .sup, target absolute percentage, or target RGB value.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Using a reference file
  supmapper.py /path/to/subtitles --reference /path/to/reference.sup
  supmapper.py /path/to/subtitles -r /path/to/reference.sup
  
  Using a target percentage
  supmapper.py "/path/to/subtitles" --percent 60.5
  supmapper.py "/path/to/subtitles" -p 60.5
  
  Using a target RGB value
  supmapper.py "/path/to/subtitles" --rgb 180
        """
    )
    
    parser.add_argument(
        "input_dirs",
        nargs='*',
        type=Path,
        help="Path(s) to the folder(s) containing .sup files to tonemap"
    )
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "-r", "--reference",
        type=Path,
        help="Path to the reference .sup file for auto-matching brightness"
    )
    group.add_argument(
        "-p", "--percent",
        type=float,
        help="Target tonemap percentage (1-100)"
    )
    group.add_argument(
        "--rgb",
        type=int,
        help="Target RBG value (0-255)"
    )
    
    args = parser.parse_args()
    
    # validate input directory
    for input_dir in args.input_dirs:
        if not input_dir.is_dir():
            print(f"Error: Folder does not exist: {input_dir}")
            exit(1)
    
    reference_max_rgb = None
    target_percent = None
    target_rgb = None
    
    # check which arguments were provided
    if args.reference:
        # reference file mode
        if not args.reference.is_file() or args.reference.suffix.lower() != ".sup":
            print(f"Error: Invalid reference file: {args.reference}")
            exit(1)
        
        print(f"\nAnalyzing reference: {args.reference.name}")
        reference_max_rgb = find_max_rgb_in_sup(str(args.reference))
        #reference_max_rgb = calculate_displayed_brightness(find_max_rgb_in_sup(str(args.reference)))
        print(f"  Reference max RGB: {reference_max_rgb}")
        
    elif args.percent:
        # percentage mode
        target_percent = args.percent
    elif args.rgb:
        target_rgb = args.rgb
    
    # create output directory(s)
    for input_dir in args.input_dirs:
        output_dir = input_dir / "Tonemapped_Subtitles"
        output_dir.mkdir(exist_ok=True)
    
    # process all .sup files
    for input_dir in args.input_dirs:
        sup_files = list(input_dir.glob("*.sup"))
        pgs_files = []
        print(f"\nAnalyzing subtitle files in {input_dir}")
        for sup_file in sup_files:
            pgs_file = PGSFile(sup_file, find_max_rgb_in_sup(sup_file))
            pgs_files.append(pgs_file)
            print(f"  {pgs_file.path.name}: max RGB = {pgs_file.max_rgb}")
            
        print("\nTonemapping subtitle files...")
        for pgs in pgs_files:
            tonemapped_pgs = None
            if args.reference:
                target_percent = (reference_max_rgb / pgs.max_rgb) * 100
                if reference_max_rgb != pgs.max_rgb:
                    tonemapped_pgs = tonemap(pgs, target_percent)
                else:
                    tonemapped_pgs = pgs.path
            elif args.percent:
                # get the factor to multiply the target percentage by
                # to tonemap the .sup as if it were pure white
                if not pgs.max_rgb >= 255:
                    norm_factor = 255 / pgs.max_rgb
                else:
                    norm_factor = 1.0
    
                tonemapped_pgs = tonemap(pgs, norm_factor * target_percent)
            elif args.rgb:
                target_percent = (args.rgb / pgs.max_rgb) * 100
                tonemapped_pgs = tonemap(pgs, target_percent)
                
            print(f"  RGB after tonemap: {find_max_rgb_in_sup(tonemapped_pgs)} ({tonemapped_pgs.name}) \n")
            
        output_dir = input_dir / "Tonemapped_Subtitles"
        print(f"Tonemapped subtitles saved to: {output_dir}\n")

