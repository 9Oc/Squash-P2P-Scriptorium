"""
suppf.py v1.1
@author squash

suppf is PGS subtitle palette fixer that corrects common subtitle color issues.

Note that this script should not be used on subtitles which are
intentionally color coded such as SDH based color coding.

Usage:
  python suppf.py input.sup output.sup
  python suppf.py input.sup output.sup --main-color yellow
  python suppf.py input.sup output.sup --main-color blue
  python suppf.py input.sup output.sup --main-color a7a792
  append --quiet for no debug output
"""
import sys
import os
import struct
import math
import argparse

# color helpers
def clamp(v):
    return max(0, min(255, int(round(v))))

def ycrcb_to_rgb(Y, Cr, Cb):
    y = float(Y)
    cr = float(Cr) - 128.0
    cb = float(Cb) - 128.0
    r = y + 1.402 * cr
    g = y - 0.344136 * cb - 0.714136 * cr
    b = y + 1.772 * cb
    return clamp(r), clamp(g), clamp(b)

def rgb_to_ycrcb(r, g, b):
    R = float(r); G = float(g); B = float(b)
    Y  = 0.299    * R + 0.587    * G + 0.114    * B
    Cb = -0.168736* R - 0.331264 * G + 0.5      * B + 128.0
    Cr = 0.5      * R - 0.418688 * G - 0.081312 * B + 128.0
    return clamp(Y), clamp(Cr), clamp(Cb)

def rgb_to_hsl(r, g, b):
    """Convert RGB to HSL for more accurate color analysis"""
    r, g, b = r/255.0, g/255.0, b/255.0
    max_val = max(r, g, b)
    min_val = min(r, g, b)
    h, s, l = 0, 0, (max_val + min_val) / 2
    
    if max_val == min_val:
        h = s = 0  # achromatic
    else:
        d = max_val - min_val
        s = d / (2 - max_val - min_val) if l > 0.5 else d / (max_val + min_val)
        if max_val == r:
            h = (g - b) / d + (6 if g < b else 0)
        elif max_val == g:
            h = (b - r) / d + 2
        elif max_val == b:
            h = (r - g) / d + 4
        h /= 6
    
    return h * 360, s * 100, l * 100

def is_grayish(r, g, b, tol=20):
    """
    Returns true if the color is grayscale.
    
    By default, grayscale is defined as any color which has its R, G, and B
    values differ by no more than 20.
    
    To restrict the number of RGB colors this function returns true for,
    lower the tolerance. To expand the number, increase the tolerance.
    """
    return abs(r - g) <= tol and abs(r - b) <= tol and abs(g - b) <= tol

def is_blackish(r, g, b, threshold=60):
    """
    Returns true if the color is a shade of black.
    These colors are most likely outlines or shadows.
    """
    return max(r, g, b) < threshold

def detect_main_text_color(all_entries):
    """
    Detect the main text color from all palette entries.
    Returns the RGB color that's most likely the main text color.
    """
    candidates = []
    
    for entries in all_entries:
        for e in entries:
            r, g, b = ycrcb_to_rgb(e["Y"], e["Cr"], e["Cb"])
            a = e["A"]
            
            # skip entries that are semi-transparent or fully transparent
            if a <= 128 or is_blackish(r, g, b, threshold=80):
                continue

            # skip existing grayscale (likely already good anti-aliasing)
            # this check will be bypassed by map_rgba_universal if a main
            # text color is user-specified.
            if is_grayish(r, g, b, tol=25):
                continue
            
            # calculate color prominence; bright, saturated colors score higher
            luminance = 0.299 * r + 0.587 * g + 0.114 * b
            h, s, l = rgb_to_hsl(r, g, b)
            
            # score based on brightness and saturation (main text is usually bright and saturated)
            score = luminance * 0.7 + s * 0.3
            
            candidates.append((score, r, g, b, luminance, s))
    
    if not candidates:
        return None
        
    # sort by score and return the highest scoring color
    candidates.sort(reverse=True)
    _, r, g, b, _, _ = candidates[0]
    return (r, g, b)

def is_similar_color(r1, g1, b1, r2, g2, b2, tolerance=40):
    """Check if two colors are similar within tolerance"""
    return (abs(r1 - r2) + abs(g1 - g2) + abs(b1 - b2)) <= tolerance

def is_main_text_color(r, g, b, target_color, tolerance=40, user_specified=False):
    """
    Check if this color is the main text color or a gradient of it.
    
    If user_specified=True we relax tests and allow grayish/pale matches
    so the explicitly provided --main-color is always recognized.
    """
    if target_color is None:
        return False
    
    tr, tg, tb = target_color
    
    # when user specified the color, be more lenient
    if user_specified:
        tol = max(tolerance, 80)
    else:
        tol = tolerance

    # direct color match (lenient or strict depending on user_specified)
    if is_similar_color(r, g, b, tr, tg, tb, tol):
        return True
    
    # check if it's a darker version (gradient) of the main color
    # same hue but lower brightness could be a gradient
    h1, s1, l1 = rgb_to_hsl(r, g, b)
    h2, s2, l2 = rgb_to_hsl(tr, tg, tb)
    
    # compute hue difference allowing wrap-around
    hue_diff = abs(h1 - h2)
    if hue_diff > 180:
        hue_diff = 360 - hue_diff

    # if user specified a color, accept looser hue and saturation matches,
    # and allow matches where luminance is reasonably close (to account for pale/grayish text)
    if user_specified:
        if hue_diff < 60 and abs(s1 - s2) < 50 and (l1 <= l2 + 20):
            return True
        # also allow a luminance-only match for very gray/pale variants
        if abs(l1 - l2) < 18:
            return True
    else:
        # for auto detection, be stricter: similar hue and lower luminance (gradient)
        if hue_diff < 30 and abs(s1 - s2) < 30 and l1 < l2:
            return True
    
    return False

def is_artifact_color(r, g, b, main_color=None):
    # artifact detection for various color combinations
    # red and blue both higher than green (magenta/purple family)
    if r > g and b > g:
        rb_avg = (r + b) / 2
        if rb_avg > g + 30:
            return True
        if abs(r - b) < 40 and min(r, b) > g + 25:
            return True
    
    # dark purples that might be missed
    if r > 50 and b > 50 and g < min(r, b) - 20:
        return True
    
    # if we know the main color, detect colors that are artifacts relative to it
    if main_color:
        mr, mg, mb = main_color
        main_h, main_s, main_l = rgb_to_hsl(mr, mg, mb)
        h, s, l = rgb_to_hsl(r, g, b)
        
        # colors with very different hue but high saturation are likely artifacts
        hue_diff = abs(h - main_h)
        if hue_diff > 180:  # handle hue wraparound
            hue_diff = 360 - hue_diff
            
        if hue_diff > 60 and s > 50: 
            return True
    
    # general artifact patterns - highly saturated, unnatural colors
    h, s, l = rgb_to_hsl(r, g, b)
    
    # saturated colors that aren't primary colors
    if s > 80 and l > 20 and l < 80:
        # exclude colors that might be legitimate main text
        if not (h < 30 or h > 330):    # not red
            if not (160 < h < 200):    # not blue  
                if not (45 < h < 75):  # not yellow
                    return True
    
    return False

def map_rgba_universal(r, g, b, a, main_color=None, user_specified=False):
    """
    Universal color mapping for fixing the bad colors -> grayscale
    Sets artifact colors to 0 alpha
    Converts main text color to grayscale while preserving luminance gradients
    Preserves grayscale anti-aliasing and black outlines
    """
    # skip transparent pixels
    if a == 0:
        return (r, g, b, a)
    
    # remove artifact colors
    if is_artifact_color(r, g, b, main_color):
        return (0, 0, 0, 0)
    
    # preserve black/dark colors (likely outlines)
    if is_blackish(r, g, b):
        return (r, g, b, a)
    
    # preserve existing grayscale (anti-aliasing) unless user explicitly specified this as main color
    if is_grayish(r, g, b) and not (user_specified and main_color and is_main_text_color(r, g, b, main_color, user_specified=True)):
        return (r, g, b, a)
    
    # convert main text color and its gradients to white-based
    if main_color and is_main_text_color(r, g, b, main_color, user_specified=user_specified):
        # calculate luminance
        luminance = 0.299 * r + 0.587 * g + 0.114 * b
        
        if luminance > 240:
            return (255, 255, 255, a)
        elif luminance > 200:
            gray_val = int(luminance * 0.95 + 12)
            return (clamp(gray_val), clamp(gray_val), clamp(gray_val), a)
        elif luminance > 160:
            gray_val = int(luminance * 0.9 + 25)
            return (clamp(gray_val), clamp(gray_val), clamp(gray_val), a)
        else:
            gray_val = int(luminance)
            return (clamp(gray_val), clamp(gray_val), clamp(gray_val), a)
    
    # for any remaining colors, convert to grayscale based on luminance
    # this handles edge cases and maintains gradients
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    gray_val = int(luminance)
    return (clamp(gray_val), clamp(gray_val), clamp(gray_val), a)

# PGS parsing
def parse_segments(data):
    segs = []
    pos = 0
    L = len(data)
    while pos + 13 <= L:
        hdr = data[pos:pos+13]
        magic, pts, dts, seg_type, seg_size = struct.unpack_from(">2sIIBH", hdr, 0)
        if magic != b'PG':
            next_pg = data.find(b'PG', pos+1)
            if next_pg == -1:
                break
            pos = next_pg
            continue
        body_start = pos + 13
        body_end = body_start + seg_size
        if body_end > L:
            break
        segs.append({
            "magic": magic,
            "pts": pts,
            "dts": dts,
            "type": seg_type,
            "size": seg_size,
            "body": bytearray(data[body_start:body_end]),
            "header_offset": pos
        })
        pos = body_end
    return segs

def build_segment_bytes(seg):
    header = struct.pack(">2sIIBH", seg["magic"], seg["pts"], seg["dts"], seg["type"], seg["size"])
    return header + bytes(seg["body"])

def parse_pds_entries(body):
    if len(body) < 5:
        return (None, None, [])
    if (len(body) - 2) % 5 == 0:
        pid = body[0]
        pver = body[1]
        entries = []
        i = 2
        while i + 5 <= len(body):
            entry_id = body[i]
            Y = body[i+1]
            Cr = body[i+2]
            Cb = body[i+3]
            A = body[i+4]
            entries.append({"entry_id": entry_id, "Y": Y, "Cr": Cr, "Cb": Cb, "A": A})
            i += 5
        return (pid, pver, entries)
    if len(body) % 5 == 0:
        entries = []
        i = 0
        while i + 5 <= len(body):
            entry_id = body[i]
            Y = body[i+1]
            Cr = body[i+2]
            Cb = body[i+3]
            A = body[i+4]
            entries.append({"entry_id": entry_id, "Y": Y, "Cr": Cr, "Cb": Cb, "A": A})
            i += 5
        return (None, None, entries)
    if len(body) >= 2:
        pid = body[0]
        pver = body[1]
        entries = []
        i = 2
        while i + 5 <= len(body):
            entry_id = body[i]
            Y = body[i+1]
            Cr = body[i+2]
            Cb = body[i+3]
            A = body[i+4]
            entries.append({"entry_id": entry_id, "Y": Y, "Cr": Cr, "Cb": Cb, "A": A})
            i += 5
        return (pid, pver, entries)
    return (None, None, [])

def build_pds_body(pid, pver, entries):
    if pid is not None:
        out = bytearray([pid, pver])
    else:
        out = bytearray()
    for e in entries:
        out.extend([e["entry_id"], e["Y"], e["Cr"], e["Cb"], e["A"]])
    return bytes(out)

def parse_main_color_arg(color_str):
    """Parse main color argument"""
    if not color_str or color_str.lower() == 'auto':
        return None
    
    color_str = color_str.lower()
    
    color_map = {
        'yellow': (255, 255, 0),
        'blue': (0, 100, 255),
        'cyan': (0, 255, 255),
        'green': (0, 255, 0),
        'red': (255, 0, 0),
        'orange': (255, 165, 0),
        'purple': (128, 0, 128),
        'pink': (255, 192, 203),
        'lime': (50, 205, 50),
    }
    
    if color_str in color_map:
        return color_map[color_str]
    
    # parse hex color (#RRGGBB or RRGGBB)
    if color_str.startswith('#'):
        color_str = color_str[1:]
    
    if len(color_str) == 6:
        try:
            r = int(color_str[0:2], 16)
            g = int(color_str[2:4], 16) 
            b = int(color_str[4:6], 16)
            return (r, g, b)
        except ValueError:
            pass
    
    return None

def process_file(in_path, out_path, main_color_arg=None, verbose=True):
    with open(in_path, "rb") as f:
        data = f.read()

    segs = parse_segments(data)
    if verbose:
        print(f"Found {len(segs)} segments.")

    # collect all palette entries for auto-detection
    all_entries = []
    pds_segments = []
    
    for si, seg in enumerate(segs):
        if seg["type"] == 0x14:  # PDS
            pid, pver, entries = parse_pds_entries(seg["body"])
            if entries:
                all_entries.append(entries)
                pds_segments.append((si, seg, pid, pver, entries))

    # set main color based on provided argument
    main_color = parse_main_color_arg(main_color_arg)
    user_specified = (main_color_arg is not None)
    
    if main_color is None:
        main_color = detect_main_text_color(all_entries)
        if main_color and verbose:
            print(f"Auto-detected main text color: RGB{main_color}")
    elif verbose:
        print(f"Using specified main text color: RGB{main_color}")

    if main_color is None and verbose:
        print("Warning: Could not detect main text color. Using fallback detection.")

    changed = False
    for si, seg, pid, pver, entries in pds_segments:
        if verbose:
            print(f"\nPDS segment #{si} at offset {seg['header_offset']} (pid={pid} ver={pver})")
            print("Before:")
            for e in entries:
                r,g,b = ycrcb_to_rgb(e["Y"], e["Cr"], e["Cb"])
                a = e["A"]
                color_type = ""
                if is_artifact_color(r, g, b, main_color):
                    color_type = " [ARTIFACT]"
                elif main_color and is_main_text_color(r, g, b, main_color, user_specified=user_specified) and a > 240:
                    color_type = " [MAIN TEXT]"
                elif is_grayish(r, g, b):
                    color_type = " [GRAYSCALE]"
                elif is_blackish(r, g, b):
                    color_type = " [BLACK/OUTLINE]"
                print(f"  id={e['entry_id']:02x}  RGB=({r:3d},{g:3d},{b:3d})  A={e['A']:3d}{color_type}")

        # map entries
        new_entries = []
        for e in entries:
            r,g,b = ycrcb_to_rgb(e["Y"], e["Cr"], e["Cb"])
            a = e["A"]
            nr, ng, nb, na = map_rgba_universal(r, g, b, a, main_color, user_specified=user_specified)
            y2, cr2, cb2 = rgb_to_ycrcb(nr, ng, nb)
            new_entries.append({"entry_id": e["entry_id"], "Y": y2, "Cr": cr2, "Cb": cb2, "A": na})

        new_body = build_pds_body(pid, pver, new_entries)
        if len(new_body) != len(seg["body"]):
            print("WARNING: new PDS body length differs from original; skipping modification for safety.")
            continue

        if new_body != bytes(seg["body"]):
            seg["body"] = bytearray(new_body)
            seg["size"] = len(new_body)
            changed = True
            if verbose:
                print("After:")
                for e in new_entries:
                    r,g,b = ycrcb_to_rgb(e["Y"], e["Cr"], e["Cb"])
                    print(f"  id={e['entry_id']:02x}  RGB=({r:3d},{g:3d},{b:3d})  A={e['A']:3d}")
        else:
            if verbose:
                print("No changes applied to this PDS (already matched).")

    # If the user explicitly requested a main color, force writing the output even
    # if the palette bytes looked identical after roundtrip. This matches user intent.
    if not changed and user_specified:
        if verbose:
            print("No byte-level changes detected, but --main-color was provided: forcing output write.")
        changed = True

    if not changed:
        print("No changes were needed. No output file written.")
        return

    # rebuild the PGS file
    out = bytearray()
    last_pos = 0
    for seg in segs:
        hdr_off = seg["header_offset"]
        if hdr_off > last_pos:
            out.extend(data[last_pos:hdr_off])
        out.extend(build_segment_bytes(seg))
        last_pos = hdr_off + 13 + len(seg["body"])

    if last_pos < len(data):
        out.extend(data[last_pos:])

    # create backup
    bak = in_path + ".orig_bak"
    if not os.path.exists(bak):
        print(f"Creating backup: {bak}")
        with open(bak, "wb") as f:
            f.write(data)
    else:
        print(f"Backup already exists: {bak}")

    with open(out_path, "wb") as f:
        f.write(out)
    print(f"Wrote fixed file: {out_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Universal PGS subtitle palette fixer - converts ugly text colors to clean white while preserving gradients and removing artifacts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python suppf.py input.sup output.sup
  python suppf.py input.sup output.sup --main-color yellow
  python suppf.py input.sup output.sup --main-color blue  
  python suppf.py input.sup output.sup --main-color FF6600
  python suppf.py input.sup output.sup --main-color --quiet

Supported color names: yellow, blue, cyan, green, red, orange, purple, pink, lime
Or use hex format: RRGGBB (e.g., FF6600)
        """)
    
    parser.add_argument("input", help="Input .sup file")
    parser.add_argument("output", help="Output .sup file")  
    parser.add_argument("--main-color", 
                       help="Main text color to convert (auto-detect if not specified). Supports color names or hex #RRGGBB")
    parser.add_argument("--quiet", "-q", action="store_true", 
                       help="Quiet mode - minimal output")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input):
        print(f"Error: Input file not found: {args.input}")
        sys.exit(1)
    
    verbose = not args.quiet
    process_file(args.input, args.output, args.main_color, verbose)

