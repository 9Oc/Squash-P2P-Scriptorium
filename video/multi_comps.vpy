# Dependencies | DO NOT EDIT
from vstools import vs, core, set_output
from awsmfunc import FrameInfo, fixlvls, MapDolbyVision
from awsmfunc.types.placebo import PlaceboColorSpace as ColorSpace
from awsmfunc.types.placebo import PlaceboTonemapFunction as Tonemap
from awsmfunc.types.placebo import PlaceboGamutMapping as Gamut
from awsmfunc.types.placebo import PlaceboHdrMetadataType as HdrMetaType
from enum import Enum, auto
from pathlib import Path

# vspreview comparison script.
# Author: squash
# Date: 17/2/2026
# Version: 2.08

# Marker objects | DO NOT EDIT
class _SkipMarker:
    def __str__(self):
        return "Skip"
class _LumaMarker:
    def __str__(self):
        return "Luma"
class _HDRMarker:
    def __str__(self):
        return "HDR10"
class _HDR10PlusMarker:
    def __str__(self):
        return "HDR10+"
class _DOVIMarker:
    def __str__(self):
        return "DOVI"
class _FPSMarker:
    def __str__(self):
        return "No FPS change"
class Resize:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
    def __str__(self):
        return f"({self.width}x{self.height})"
class Crop:
    def __init__(self, left: int, right: int, top: int, bottom: int):
        self.left = left
        self.right = right
        self.top = top
        self.bottom = bottom
    def __str__(self):
        return f"(Left:{self.left},Right:{self.right},Top:{self.top},Bottom:{self.bottom})"
class AddBorders:
    def __init__(self, left: int, right: int, top: int, bottom: int):
        self.left = left
        self.right = right
        self.top = top
        self.bottom = bottom
    def __str__(self):
        return f"(Left:{self.left},Right:{self.right},Top:{self.top},Bottom:{self.bottom})"
class Pad:
    def __init__(self, positions: list[int], counts: list[int] | int = 1):
        if isinstance(counts, int):
            counts = [counts] * len(positions)
        if len(positions) != len(counts):
            raise ValueError("positions and counts must have the same length if counts is a list")

        self.positions = positions
        self.counts = counts
    def __str__(self):
        return "(" + ", ".join(f"after {p}: {c} blank frame(s)" for p, c in zip(self.positions, self.counts)) + ")"
class Decimate:
    def __init__(self, order):
        self.order = order
    def __str__(self):
        return f"Field order ({ {1: 'Top', 0: 'Bottom'}.get(self.order, 'Unknown') })"
class BakeEL:
    def __init__(self, el_path: str):
        self.el_path = el_path
    def __str__(self):
        return f"(EL: {self.el_path})"
class Engine(Enum):
    BESTSOURCE = auto()
    FFMS2 = auto()
    LSMASH = auto()
    
    def __str__(self):
        return {
            Engine.BESTSOURCE: "BestSource",
            Engine.FFMS2: "ffms2",
            Engine.LSMASH: "LSMASH",
        }[self]
    

Skip = _SkipMarker()
Luma = _LumaMarker()
HDR = _HDRMarker()
HDR10Plus = _HDR10PlusMarker()
DOVI = _DOVIMarker()
NoFPS = _FPSMarker()

##########
# Config #
##########
# Required Arguments:
#   - filepath (single string or tuple of strings for seamless branching discs)
#   - name (the name of the clip to be displayed with FrameInfo)
# Optional Arguments:
#   - Trimming:
#       - int → trim N frames from the start of the clip
#       - tuple of 2 ints → (start, end) trim frames between start and end
#       - list of tuples containing 2 ints each → multiple trim ranges, example: [(500, 506), (11501, 11598), (67801, 68000)]
#       - Omit trim value(s) to keep clip untouched
#   - Padding:
#       - Pad(positions, counts) → pads frames after the frames specified in positions
#       - positions and counts are a list of ints, for example:
#       - Pad([1000, 2000], [1, 7]) would add one blank frame after frame 1000 and 7 blank frames after frame 2000
#   - Resizing:
#       - Resize(width, height) → the width and height you want to resize to
#       - Note that resizing is applied to the clip before cropping
#   - Cropping:
#       - Crop(left, right, top, bottom) → values to crop the clip with
#   - Adding Borders:
#       - AddBorders(left, right, top, bottom) → values to add black borders to the clip with
#   - Decimate:
#       - Decimate(order) → Decimates duplicate frames in telecined video sources
#       - order is an int, accepted values are 0 or 1 (0 for Bottom Field, 1 for Top Field)
#   - Luma Adjustment:
#       - Luma → Applies luminance correction to the clip to fix clips that suffer from the 0.88 gamma bug
#   - Tonmapping:
#       - HDR → tonemap the clip using HDR10 metadata
#       - HDR10Plus → tonemap the clip using HDR10+ metadata
#       - DOVI → tonemap the clip using Dolby Vision metadata
#   - FPS Adjustment:
#       - NoFPS → prevents the clip from having its framerate normalized
#       - Note that by default, all clips are normalized to the FPS value set below with fpsnum, fpsden
#   - Bake Enhancement Layer:
#       - BakeEL(path) → Bakes the Dolby Vision enhancement layer into the video stream
#       - Provide the file path to the EL.mkv as an argument
#   - Skip:
#       - Skip → Skips the clip for output in vspreview
#   - Engine:
#       - Sets the video indexing engine to one of the three available options in VapourSynth. Defaults to using LSMASH.
#       - Engine.LSMASH → Sets the video indexing engine to be LSMASH.
#       - Engine.BESTSOURCE → Sets the video indexing engine to be BestSource.
#       - Engine.FFMS2 → Sets the video indexing engine to be ffms2.
# Examples:
#   (r"file1.mkv", "Source1", (10, 200), Crop(0, 0, 140, 140))
#   (r"file2.EVO", "Source2", 24, HDR)
#   (r"file3.vob", "Source3", Luma, NoFPS)
#   ((r"part1.m2ts", r"part2.m2ts"), "Source4", Resize(1920, 1080), DOVI)
#   (r"00002.m2ts", "Source5", AddBorders(0, 0, 140, 140), HDR10Plus, Pad([10000],[20]), Engine.FFMS2)
clips_config = [
    (r"", "Source1",),
    (r"", "Source2",),
    (r"", "Source3",),
    (r"", "Source4",),
    (r"", "Source5",),
    (r"", "Source6",),
    (r"", "Source7",),
    (r"", "Source8",),
    (r"", "Source9",),
]

# The framerate to normalize all clips to
fpsnum, fpsden = 24000, 1001

# Tonemap dicts | DO NOT EDIT
vsplacebo_hdr = {
    "src_csp": ColorSpace.HDR10,
    "dst_csp": ColorSpace.SDR,
    "dynamic_peak_detection": False,
    "gamut_mapping": Gamut.Perceptual,
    "tone_mapping_function": Tonemap.Mobius,
    "metadata": HdrMetaType.HDR10,
    "use_dovi": False,
    "contrast_recovery": 0.0,
}
vsplacebo_hdr10p = {
    "src_csp": ColorSpace.HDR10,
    "dst_csp": ColorSpace.SDR,
    "dynamic_peak_detection": False,
    "gamut_mapping": Gamut.Perceptual,
    # ST2094_40 is theoretically more accurate for dynamic HDR10+ metadata, but if the result is
    # not satisfactory, Mobius can be substituted
    "tone_mapping_function": Tonemap.ST2094_40,
    "metadata": HdrMetaType.HDR10Plus,
    "use_dovi": False,
    "contrast_recovery": 0.0,
}
vsplacebo_dovi = {
    "src_csp": ColorSpace.DOVI,
    "dst_csp": ColorSpace.SDR,
    "dynamic_peak_detection": False,
    "gamut_mapping": Gamut.Perceptual,
    "tone_mapping_function": Tonemap.Mobius,
    "use_dovi": True,
    "contrast_recovery": 0.0,
}

# Helper functions | DO NOT EDIT
def trim_frames(clip: vs.VideoNode, trims):
    """
    Delete frames using std.DeleteFrames.
    Argument:
      - None: no trimming
      - int: delete frames from start up to this frame (exclusive)
      - tuple: (start, end) single trim range [inclusive]
      - list of tuples: multiple trim ranges [inclusive]
    Frame numbers are interpreted sequentially on the current clip,
    so they match what you see in vspreview after previous trims.
    """
    if trims is None:
        return clip

    if isinstance(trims, int):
        trims = [(0, trims - 1)]
    elif isinstance(trims, tuple) and len(trims) == 2:
        trims = [trims]

    for start, end in trims:
        if start > end:
            raise ValueError(f"Start {start} cannot be greater than end {end}")
        clip = core.std.DeleteFrames(clip, list(range(start, end + 1)))

    return clip
    
def insert_blank_frames(clip: vs.VideoNode, positions: list[int], counts: list[int] | int = 1) -> vs.VideoNode:
    """
    Insert blank frames at specific positions, treating positions as 
    target indices in the output timeline.
    """
    if isinstance(counts, int):
        counts = [counts] * len(positions)
    if len(positions) != len(counts):
        raise ValueError("Positions and counts must have the same length if counts is a list.")
    
    # sort by position to handle them in order
    pairs = sorted(zip(positions, counts), key=lambda x: x[0])
    
    out = []
    prev_original_idx = 0
    cumulative_offset = 0
    
    for pos, count in pairs:
        # we need to find where this frame is in the original source
        # the target position 'pos' includes the 'cumulative_offset' of frames we added previously
        # so, the original source index is: pos - cumulative_offset
        current_original_idx = pos - cumulative_offset
        
        # check to ensure we haven't asked for a position that doesn't exist yet
        # (e.g., trying to insert at frame 100 when we've only processed 50 source frames)
        if current_original_idx < prev_original_idx:
             raise ValueError(f"Position {pos} overlaps with previous insertions.")

        # slice from where we left off up to the calculated source index
        # we use current_original_idx + 1 because we want to include the frame at that index before the blank
        out.append(clip[prev_original_idx : current_original_idx + 1])
        
        # add the blank frames
        out.append(core.std.BlankClip(clip, length=count))
        
        # update trackers
        prev_original_idx = current_original_idx + 1
        cumulative_offset += count
    
    # append whatever is left of the original clip
    out.append(clip[prev_original_idx:])
    
    return core.std.Splice(clips=out, mismatch=True)


##############
# Processing # DO NOT EDIT
##############
for entry in clips_config:
    skip = False
    filepath, filename, srcname = None, None, None
    trim_range = None
    padding = None
    resize = None
    crop_values = None
    borders = None
    decimate = None
    luma = False
    tonemap_mode = None
    change_fps = True
    el_path = None
    engine = None

    for param in entry:
        if param is Skip:
            skip = True
            break
        elif isinstance(param, str): # single video file
            if param.lower().endswith((".m2ts", ".h264", ".avc", ".h265", ".hevc", ".mkv", ".evo",
                                       ".vob", ".mp4", ".m2v", ".mpg", ".mpeg", ".avi",)):
                filepath = param
                filename = Path(filepath).name
            else:
                srcname = param # otherwise, string is srcname
        elif isinstance(param, tuple): # tuple is either multiple video files or trim range
            if all(isinstance(p, str) for p in param):
                filepath = param
                filename = tuple(Path(p).name for p in filepath)
            elif len(param) == 2:
                trim_range = param
        elif isinstance(param, list) and all(isinstance(x, tuple) for x in param): # multiple trim ranges
            if all(isinstance(x, tuple) and len(x) == 2 and all(isinstance(v, int) for v in x) for x in param):
                trim_range = param
        elif isinstance(param, int): # int is a single trim value
            trim_range = param
        elif isinstance(param, Pad):
            padding = param
        elif isinstance(param, Crop):
            crop_values = param
        elif isinstance(param, Resize):
            resize = param
        elif isinstance(param, Decimate):
            decimate = param
        elif param is Luma:
            luma = True
        elif param in (HDR, HDR10Plus, DOVI):
            tonemap_mode = param
        elif param is NoFPS:
            change_fps = False
        elif isinstance(param, BakeEL):
            el_path = param.el_path
        elif isinstance(param, AddBorders):
            borders = param
        elif isinstance(param, Engine):
            engine = param

    if skip:
        print("Skipping...")
        continue
    if not filepath or not srcname:
        print("No filepath or source name detected, skipping...")
        continue

    if engine is None:
        engine = Engine.LSMASH

    print(f"Loading clip: {filename} ({srcname})")
    options = [
        (engine,       f"Engine: {engine}"),
        (change_fps,   f"Normalize FPS: {change_fps}"),
        (trim_range,   f"Trim: {trim_range}"),
        (padding,      f"Pad: {padding}"),
        (resize,       f"Resize: {resize}"),
        (crop_values,  f"Crop: {crop_values}"),
        (borders,      f"Borders: {borders}"),
        (decimate,     f"Decimate: {decimate}"),
        (tonemap_mode, f"Tonemapping: {tonemap_mode}"),
        (luma,         f"Luma adjustment: {luma}"),
        (el_path,      f"Baking EL: {el_path}")
    ]

    items = [text for enabled, text in options if enabled]

    for i, text in enumerate(items):
        branch = "└──" if i == len(items) - 1 else "├──"
        print(f"  {branch} {text}")

    clip = None

    # Load clip(s)
    if isinstance(filepath, tuple):
        if engine is Engine.LSMASH:
            clips = [core.lsmas.LWLibavSource(p) for p in filepath]
        elif engine is Engine.FFMS2:
            clips = [core.ffms2.Source(p) for p in filepath]
        elif engine is Engine.BESTSOURCE:
            clips = [core.bs.VideoSource(p) for p in filepath]
        clip = clips[0]
        for c in clips[1:]:
            clip += c
    else:
        if engine is Engine.LSMASH:
            clip = core.lsmas.LWLibavSource(filepath)
        elif engine is Engine.FFMS2:
            clip = core.ffms2.Source(filepath)
        elif engine is Engine.BESTSOURCE:
            clip = core.bs.VideoSource(filepath)

    # Decimate telecined video sources
    if decimate:
        clip = core.vivtc.VFM(clip, decimate.order)
        clip = core.vivtc.VDecimate(clip)

    # Bake EL if provided
    clip_el_baked = None
    if el_path:
        el = core.lsmas.LWLibavSource(el_path)
        clip_el_baked = MapDolbyVision(clip, el)
        clip = clip_el_baked

    # Change FPS
    if change_fps:
        clip = core.std.AssumeFPS(clip, fpsnum=fpsnum, fpsden=fpsden)

    # Trim
    if trim_range:
        clip = trim_frames(clip, trim_range)

    # Pad
    if padding:
        clip = insert_blank_frames(clip, padding.positions, padding.counts)

    # Resize
    if resize:
        needs_resampling = resize.width % 2 != 0 or resize.height % 2 != 0
        if (needs_resampling):
            clip = clip.resize.Bicubic(format=vs.YUV444P16)
        clip = clip.resize.Spline36(resize.width, resize.height, dither_type="error_diffusion")
        if (clip.width % 2 == 0 and clip.height % 2 == 0):
            clip = clip.resize.Bicubic(format=vs.YUV420P10)

    # Crop
    if crop_values:
        l = crop_values.left
        r = crop_values.right
        t = crop_values.top
        b = crop_values.bottom
        needs_resampling = any(v % 2 for v in(l,r,t,b))
        if (needs_resampling):
            clip = clip.resize.Bicubic(format=vs.YUV444P16)
        clip = core.std.CropRel(clip, l, r, t, b)
        if (clip.width % 2 == 0 and clip.height % 2 == 0):
            clip = clip.resize.Bicubic(format=vs.YUV420P10)

    # Add Borders
    if borders:
        if any(v % 2 for v in (borders.left, borders.right, borders.top, borders.bottom)):
            clip = clip.resize.Bicubic(format=vs.YUV444P16)
        clip = core.std.AddBorders(clip, borders.left, borders.right, borders.top, borders.bottom)
        if (clip.width % 2 == 0 and clip.height % 2 == 0):
            clip = clip.resize.Bicubic(format=vs.YUV420P10)

    # Tonemap
    if tonemap_mode is not None:
        srcname += " (Tonemapped "
        clip = clip.resize.Bicubic(format=vs.YUV444P16)
        if tonemap_mode is HDR:
            srcname += "HDR)"
            clip = core.placebo.Tonemap(clip, **vsplacebo_hdr)
        elif tonemap_mode is HDR10Plus:
            srcname += "HDR10+)"
            clip = core.placebo.Tonemap(clip, **vsplacebo_hdr10p)
        else:
            srcname += "DOVI)"
            clip = core.placebo.Tonemap(clip, **vsplacebo_dovi)

        clip = core.std.SetFrameProps(
            clip, _Matrix=vs.MATRIX_BT709, _Transfer=vs.TRANSFER_BT709, _Primaries=vs.PRIMARIES_BT709
        )

    # Output
    if clip_el_baked:
        srcname += " (EL Baked)"

    if luma:
        clip = fixlvls(clip)
        srcname += " (Luma adjusted)"

    set_output(FrameInfo(clip, srcname), name=srcname)

