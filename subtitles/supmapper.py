"""
supmapper.py
@author squash
@version 2.0

Tonemap .sup files using a reference .sup file for brightness matching.
Optionally provide a relative percentage or RGB value to tonemap without a reference.
All .sup files in the given directory will be tonemapped to the given reference/percentage/RGB value.

Dependencies:
pip install git+https://github.com/cubicibo/SUPer.git@v0.3.0
SupMover https://github.com/MonoS/SupMover

SupMover must be added to your PATH with the .exe named "SupMover.exe".
"""
import argparse
import math
import shutil
import subprocess

from pathlib import Path
from SUPer import SUPReader, PDS

class PGSFile:
    def __init__(self, path, max_rgb, max_y):
        self.path = path
        self.max_rgb = max_rgb
        self.max_y = max_y
        
    def __repr__(self):
        return f"{self.path.stem}"


# YCbCr -> RGB BT.709 / BT.2020
def ycbcr_to_rgb_limited(y, cb, cr):
    y = (y - 16) * (255 / 219)
    cb = cb - 128
    cr = cr - 128
    r = y + 1.402 * cr
    g = y - 0.344136 * cb - 0.714136 * cr
    b = y + 1.772 * cb
    return tuple(int(round(max(0, min(255, v)))) for v in (r, g, b))

def find_max_rgb_y_in_sup(sup_path: str | Path) -> tuple[int, int]:
    sup_path = Path(sup_path)
    sup = SUPReader(sup_path)

    max_rgb = 0
    max_y = 0

    # SUPer 0.3.0 yields parsed segments directly; no DisplaySet assembly
    for seg in sup.read_segment():
        if isinstance(seg, PDS):
            # PDS.palette is now a dict-like Palette (ID -> PaletteEntry)
            for entry in seg.palette.values():
                if entry.A > 0:  # check visible palette entries only
                    r, g, b = ycbcr_to_rgb_limited(entry.Y, entry.Cb, entry.Cr)
                    max_rgb = max(max_rgb, r, g, b)
                    max_y = max(max_y, entry.Y)

    return max_rgb, max_y

def calculate_target_percent(current_y: float, target_y: float) -> float:
    source_y_norm = ((current_y - 16) * (255 / 219)) / 255
    target_y_norm = ((target_y - 16) * (255 / 219)) / 255
    return target_y_norm / source_y_norm
    
def tonemap(pgs: PGSFile, target_percent: float) -> Path:
    """
    Apply the specified tonemap percent the specified PGSFile.
    """
    tonemapped_file = pgs.path.parent / "Tonemapped_Subtitles" / f"{pgs.path.stem}_tonemapped.sup"
    print(f"\n  {pgs.path.name}")
    if (round(pgs.max_y * target_percent) == pgs.max_y):
        print(f"  └── Already at target brightness: {pgs.max_y}")
        shutil.copy2(pgs.path, tonemapped_file)
        return tonemapped_file
    
    print(f"  ├── Applying tonemap: {target_percent:.4f}")
    subprocess.run(["SupMover", str(pgs.path), str(tonemapped_file), "--tonemap", str(target_percent)], check=True)
    return tonemapped_file

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Tonemap PGS subtitles (.sup files) to match reference .sup, target absolute percentage, or target RGB value.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Using a reference file
  supmapper.py "/path/to/subtitles" --reference /path/to/reference.sup
  supmapper.py "/path/to/subtitles" -r /path/to/reference.sup
  
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
    
    # validate input directory(s)
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
        reference_max_rgb, reference_max_y = find_max_rgb_y_in_sup(args.reference)
        reference_pgs = PGSFile(Path(args.reference), reference_max_rgb, reference_max_y)
        print(f"  Reference max Y: {reference_pgs.max_y}")
        
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
            sup_max_rgb, sup_max_y = find_max_rgb_y_in_sup(sup_file)
            pgs_file = PGSFile(sup_file, sup_max_rgb, sup_max_y)
            pgs_files.append(pgs_file)
            print(f"  {pgs_file.path.name}: max Y = {pgs_file.max_y}")
            
        print(f"\nTonemapping subtitle files: {input_dir}")
        for pgs in pgs_files:
            if args.reference:
                target_percent = calculate_target_percent(pgs.max_y, reference_pgs.max_y)
            elif args.percent:
                # get the factor to multiply the target percentage by
                # to tonemap the .sup as if it were pure white
                if not pgs.max_y >= 235:
                    norm_factor = 235 / pgs.max_y
                else:
                    norm_factor = 1.0
                target_percent = (norm_factor * args.percent) / 100
            elif args.rgb:
                target_y = (args.rgb * 219 / 255) + 16
                target_percent = calculate_target_percent(pgs.max_y, target_y)
            
            tonemapped_pgs = tonemap(pgs, target_percent)
            tonemapped_rgb, tonemapped_y = find_max_rgb_y_in_sup(tonemapped_pgs)
            if (pgs.max_y != tonemapped_y):
                print(f"  ├── Y after tonemap: {tonemapped_y}")
                print(f"  └── RGB after tonemap: {tonemapped_rgb}")
            
        output_dir = input_dir / "Tonemapped_Subtitles"
        print(f"\nTonemapped subtitles saved to: {output_dir}")
