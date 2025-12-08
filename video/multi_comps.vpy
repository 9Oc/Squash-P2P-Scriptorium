# Dependencies
from vstools import vs, core, set_output
from awsmfunc import FrameInfo, fixlvls, MapDolbyVision
from awsmfunc.types.placebo import PlaceboColorSpace as ColorSpace
from awsmfunc.types.placebo import PlaceboTonemapFunction as Tonemap
from awsmfunc.types.placebo import PlaceboGamutMode as Gamut
from pathlib import Path

# vspreview comparison script.
# Author: squash
# Date: 10/2/2025

# Marker objects
class _LumaMarker:
    def __str__(self):
        return "Luma"
class _HDRMarker:
    def __str__(self):
        return "HDR10"
class _DOVIMarker:
    def __str__(self):
        return "DOVI"
class _FPSMarker:
    def __str__(self):
        return "No FPS change"
class _CropMarker:
    def __init__(self, left: int, right: int, top: int, bottom: int):
        self.left = left
        self.right = right
        self.top = top
        self.bottom = bottom
    def __str__(self):
        return f"(Left:{self.left},Right:{self.right},Top:{self.top},Bottom:{self.bottom})"
class _ResizeMarker:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
    def __str__(self):
        return f"({self.width}x{self.height})"
class _PadMarker:
    def __init__(self, positions: list[int], counts: list[int] | int = 1):
        if isinstance(counts, int):
            counts = [counts] * len(positions)
        if len(positions) != len(counts):
            raise ValueError("positions and counts must have the same length if counts is a list")

        self.positions = positions
        self.counts = counts
    def __str__(self):
        return "(" + ", ".join(f"after {p}: {c} blank frame(s)" for p, c in zip(self.positions, self.counts)) + ")"
class _BakeELMarker:
    def __init__(self, el_path: str):
        self.el_path = el_path
    def __str__(self):
        return f"(EL: {self.el_path})"
class _AddBordersMarker:
    def __init__(self, left: int, right: int, top: int, bottom: int):
        self.left = left
        self.right = right
        self.top = top
        self.bottom = bottom
    def __str__(self):
        return f"(Left:{self.left},Right:{self.right},Top:{self.top},Bottom:{self.bottom})"

Luma = _LumaMarker()
HDR = _HDRMarker()
DOVI = _DOVIMarker()
NoFPS = _FPSMarker()
def Crop(left, right, top, bottom):
    return _CropMarker(left, right, top, bottom)
def Resize(width, height):
    return _ResizeMarker(width, height)
def Pad(positions, counts):
    return _PadMarker(positions, counts)
def BakeEL(el):
    return _BakeELMarker(el)
def AddBorders(left, right, top, bottom):
    return _AddBordersMarker(left, right, top, bottom)

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
#   - Luma Adjustment:
#       - Luma → Output an additional clip with luma adjustment for gamma bugged discs
#   - Tonmapping:
#       - HDR → tonemap the clip using HDR10 metadata
#       - DOVI → tonemap the clip using Dolby Vision metadata
#   - FPS Adjustment:
#       - NoFPS → prevents the clip from having its framerate normalized
#       - Note that by default, all clips are normalized to the FPS value set below with fpsnum, fpsden
#   - Bake Enhancement Layer:
#       - BakeEL(path) → Bakes the Dolby Vision enhancement layer into the video stream
#       - Provide the file path to the EL.mkv as an argument
# Examples:
#   (r"file1.mkv", "Source1", (10, 200), Crop(0, 0, 140, 140))
#   (r"file2.EVO", "Source2", 24, HDR)
#   (r"file3.vob", "Source3", Luma, NoFPS)
#   ((r"part1.m2ts", r"part2.m2ts"), "Source4", Resize(1920, 1080), DOVI)
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

# Tonemap dicts
vsplacebo_hdr = {
    "src_csp": ColorSpace.HDR10,
    "dst_csp": ColorSpace.SDR,
    "dynamic_peak_detection": False,
    "gamut_mapping": Gamut.Clip,
    "tone_mapping_function": Tonemap.ST2094_40,
    "use_dovi": False,
    "contrast_recovery": 0.0,
}
vsplacebo_dovi = {
    "src_csp": ColorSpace.DOVI,
    "dst_csp": ColorSpace.SDR,
    "dynamic_peak_detection": False,
    "gamut_mapping": Gamut.Clip,
    "tone_mapping_function": Tonemap.ST2094_10,
    "use_dovi": True,
    "contrast_recovery": 0.0,
}

def trim_frames(clip: vs.VideoNode, trims):
    """
    Delete frames using std.DeleteFrames.
    Supports:
      - None: no trimming
      - int: delete frames from start up to this frame (exclusive)
      - tuple: (start, end) single trim range [inclusive]
      - list of tuples: multiple trim ranges [inclusive]
    Frame numbers are interpreted SEQUENTIALLY on the current clip,
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
    Insert blank frames after specified positions in the clip.
    Arguments:
       - clip (vs.VideoNode): Input clip.
       - positions (list[int]): List of frame indices (in the original clip) after which blank frames are inserted.
       - counts (list[int] | int): Either a single integer (same count for all positions),
                                   or a list matching `positions`.
    Returns:
        vs.VideoNode: New clip with blank frames inserted.
    """
    if isinstance(counts, int):
        counts = [counts] * len(positions)
    if len(positions) != len(counts):
        raise ValueError("Positions and counts must have the same length if counts is a list.")
    
    pairs = sorted(zip(positions, counts), key=lambda x: x[0])
    out = []
    prev = 0
    offset = 0  # track cumulative offset from inserted frames
    
    for pos, count in pairs:
        # slice from previous position to current position (in original clip)
        out.append(clip[prev:pos+1])
        # add blank frames
        out.append(core.std.BlankClip(clip, length=count))
        # update offset for next iteration
        offset += count
        prev = pos + 1
    
    # append remaining frames
    out.append(clip[prev:])
    return core.std.Splice(clips=out, mismatch=True)

##############
# Processing #
##############
for entry in clips_config:
    filepath, filename, srcname = None, None, None
    trim_range = None
    padding = None
    crop_values = None
    resize = None
    luma = False
    tonemap_mode = None
    change_fps = True
    el_path = None
    borders = None

    for param in entry:
        if isinstance(param, str): # single video file
            if param.lower().endswith((".vob", ".m2ts", ".evo", ".mkv", ".mp4", ".avi", ".h264", ".h265", ".hevc", ".avc")):
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
        elif isinstance(param, list): # list is multiple trim ranges
            if all(isinstance(x, tuple) and len(x) == 2 and all(isinstance(v, int) for v in x) for x in param):
                trim_range = param
        elif isinstance(param, int): # int is a single trim value
            trim_range = param
        elif isinstance(param, _PadMarker):
            padding = param
        elif isinstance(param, _CropMarker):
            crop_values = param
        elif isinstance(param, _ResizeMarker):
            resize = param
        elif param is Luma:
            luma = True
        elif param in (HDR, DOVI):
            tonemap_mode = param
        elif param is NoFPS:
            change_fps = False
        elif isinstance(param, _BakeELMarker):
            el_path = param.el_path
        elif isinstance(param, _AddBordersMarker):
            borders = param

    if not filepath or not srcname:
        print("No filepath or source name detected, skipping...")
        continue

    print(f"Loading clip: {filename} ({srcname})")
    print(f"Normalize FPS: {change_fps}, Trim: {trim_range}, Pad: {padding}, Resize: {resize}, Crop: {crop_values}, Borders: {borders}, Tonemapping: {tonemap_mode}, Output luma adjusted: {luma}")
    if el_path:
        print(f"Baking EL: {el_path}")
    
    # Load clip(s)
    if isinstance(filepath, tuple):
        clips = [core.lsmas.LWLibavSource(p) for p in filepath]
        clip = clips[0]
        for c in clips[1:]:
            clip += c
    else:
        clip = core.lsmas.LWLibavSource(filepath)

    # Decimate interlaced frames if clip is an interlaced NTSC DVD
    if clip.fps_num > 29000 and clip.fps_num < 31000:
        clip = core.vivtc.VFM(clip, 1)
        clip = core.vivtc.VDecimate(clip)
        
    # Bake EL if provided
    clip_el_baked = None
    if el_path:
        el = core.lsmas.LWLibavSource(el_path)
        clip_el_baked = MapDolbyVision(clip, el)
        
    # Change FPS
    if change_fps:
        clip = core.std.AssumeFPS(clip, fpsnum=fpsnum, fpsden=fpsden)
        if clip_el_baked:
            clip_el_baked = core.std.AssumeFPS(clip_el_baked, fpsnum=fpsnum, fpsden=fpsden)

    # Trim
    if trim_range:
        clip = trim_frames(clip, trim_range)
        if clip_el_baked:
            clip_el_baked = trim_frames(clip_el_baked, trim_range)
        
    # Pad
    if padding:
        clip = insert_blank_frames(clip, padding.positions, padding.counts)
        if clip_el_baked:
            clip_el_baked = insert_blank_frames(clip_el_baked, padding.positions, padding.counts)
        
    # Resize
    if resize:
        clip = clip.resize.Spline36(resize.width, resize.height, dither_type="error_diffusion")
        if clip_el_baked:
            clip_el_baked = clip_el_baked.resize.Spline36(resize.width, resize.height, dither_type="error_diffusion")

    # Crop
    if crop_values:
        clip = core.std.CropRel(clip, crop_values.left, crop_values.right, crop_values.top, crop_values.bottom)
        if clip_el_baked:
            clip_el_baked = core.std.CropRel(clip_el_baked, crop_values.left, crop_values.right, crop_values.top, crop_values.bottom)
    
    # Add Borders
    if borders:
        clip = core.std.AddBorders(clip, borders.left, borders.right, borders.top, borders.bottom)
        if clip_el_baked:
            clip_el_baked = core.std.AddBorders(clip_el_baked, borders.left, borders.right, borders.top, borders.bottom)

    # Tonemap if HDR or DOVI marker
    if tonemap_mode is not None:
        srcname += " (Tonemapped "
        clip = clip.resize.Bicubic(format=vs.YUV444P16)
        if tonemap_mode is HDR:
            srcname += "HDR)"
            clip = core.placebo.Tonemap(clip, **vsplacebo_hdr)
        else:
            srcname += "DOVI)"
            clip = core.placebo.Tonemap(clip, **vsplacebo_dovi)
            if clip_el_baked:
                clip_el_baked = clip_el_baked.resize.Bicubic(format=vs.YUV444P16)
                clip_el_baked = core.placebo.Tonemap(clip_el_baked, **vsplacebo_dovi)

        clip = core.std.SetFrameProps(
            clip, _Matrix=vs.MATRIX_BT709, _Transfer=vs.TRANSFER_BT709, _Primaries=vs.PRIMARIES_BT709
        )
        if clip_el_baked:
            clip_el_baked = core.std.SetFrameProps(
                clip_el_baked, _Matrix=vs.MATRIX_BT709, _Transfer=vs.TRANSFER_BT709, _Primaries=vs.PRIMARIES_BT709
            )

    # Output
    set_output(FrameInfo(clip, srcname), name=srcname)
    if clip_el_baked:
        src_baked_name = f"{srcname} (EL Baked)"
        set_output(FrameInfo(clip_el_baked, src_baked_name), name=src_baked_name)

    if luma:
        adj_clip = fixlvls(clip)
        set_output(FrameInfo(adj_clip, f"{srcname} (Luma adjusted)"), name=f"{srcname} (Luma adjusted)")
