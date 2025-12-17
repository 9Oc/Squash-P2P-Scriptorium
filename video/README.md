# Video Scripts
<h2><a href="https://github.com/9Oc/Squash-P2P-Script-Emporium/blob/main/video/check_idr.py">check_idr</a>
<a href="https://www.python.org/downloads/release/python-370/"><img src="https://img.shields.io/badge/Python-3.07%2B-brightgreen" alt="Python 3.07+"></a></h2>

`check_idr.py` will determine if a given frame in an h264 raw stream is an IDR frame or not.

Dependencies:

`pip install rich`

[ffmpeg](https://www.ffmpeg.org/download.html) must be installed and in your PATH.
<hr>

### Usage
A path to a raw h264 stream and a frame number are required arguments.

`check_idr.py video.h264 --frame 1000`

Adding the `--verbose` argument will output all IDR frames found up to the given frame number.
<hr>

Example output:
<img src="https://img.onlyimage.org/FtXJGy.png">

<h2><a href="https://github.com/9Oc/Squash-P2P-Scriptorium/blob/main/video/multi_comps.vpy">multi_comps</a>
<a href="https://www.python.org/downloads/release/python-3120/"><img src="https://img.shields.io/badge/Python-3.12%2B-brightgreen" alt="Python 3.12+"></a></h2>

`multi_comps.vpy` is a vspreview video comparison script. It automates much of the boilerplate code needed to compare multiple sources and supports any number of sources.

Dependencies:
- [Python 3.12](https://www.python.org/downloads/release/python-3120/): Install using  `Windows installer (64-bit)`
- [VapourSynth](https://github.com/vapoursynth/vapoursynth/releases/tag/R70): Install using  `VapourSynth-x64-R70.exe`
- [VSRepoGUI](https://github.com/theChaosCoder/VSRepoGUI/releases/tag/v0.9.8)
- [vspreview](https://github.com/Jaded-Encoding-Thaumaturgy/vs-preview): Install using  `pip install vspreview` after you've installed Python and VapourSynth

Plugins required from VSRepoGUI:
- Dovi Library
- LSMASHSource
- vs-placebo
- Subtext
- VSUtil
- RemapFrames
- FillBorders
- vivtc

Plugins required that are not on VSRepo:

`pip install awsmfunc`
<hr>

### Usage

Open `multi_comps.vpy` in a text editor or development environment of your choice.  
Then, scroll down to this section:

```python
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
```

By default, there are 9 empty clip templates for you to edit as seen above, but you can add or remove as many as you like.  
Any empty clip templates that are leftover will be skipped automatically by the script.

You can apply any combination of the clip parameters below to each clip.

---

### Clip Parameters

1. **File-path(s)**  
   A clip can be configured with a single file-path or multiple file-paths (a tuple of raw strings) that will be joined together.  
   Multiple file-paths might be used if you are comparing a disc which has seamless branching.
   
3. **Source Name**  
   The name of the source for the clip. This will appear in the upper left corner of the frame so you can easily identify what source the frame is from when generating screenshots.

4. **Trimming**  
   The frames to trim from the clip for the purpose of syncing multiple sources.  
   The trimming parameter can be any of the following formats:
   - `int`: A single integer will trim N frames from the start of the clip.
   - `tuple of 2 ints`: A tuple containing 2 integers will trim the frames between the first and second integers. Example: `(1000, 1050)` trims frames 1000–1050.
   - `list of (int, int) tuples`: Multiple trim ranges.

5. **Pad**  
   Allows for padding of blank frames into the clip for the purpose of syncing multiple sources.  
   Example:  
   `Pad([1000, 2000], [1, 7])`

6. **Resize**  
   Resizes the clip to the specified width and height.  
   Example:  
   `Resize(1920, 1080)`  
   Note that resizing will happen before cropping.

7. **Cropping**  
   Crops the clip by a tuple of 4 ints. Example:  
   `(10, 0, 22, 22)`

8. **Luma**  
   Outputs a duplicate of the clip with the luminance values adjusted to correct gamma-bugged sources.  
   Accepted value: `Luma`

9. **Tonemapping**  
   Applies tonemapping to HDR/Dolby Vision sources so they can be viewed on SDR screens.  
   Accepted values:  
   - `HDR`: Tonemaps an HDR10 source to SDR.  
   - `DOVI`: Tonemaps a Dolby Vision source to SDR using DV metadata.

10. **Baking FEL**  
   Outputs a duplicate of the clip with the Dolby Vision EL baked into the source.  
   Example:  
   `BakeEL(r"path/to/EL.mkv")`

11. **NoFPS**  
    By default, the script normalizes all clips to the same FPS value defined by `fpsnum` and `fpsden`.  
    To skip FPS normalization for a specific clip, use: `NoFPS`

---

# Examples

```
(r"G:\Hardcore.Henry.2015.MULTi.COMPLETE.BLURAY-RATPACK\BDMV\STREAM\00004.m2ts", "Capelight Pictures GER", 50)
```

Trims 50 frames off the start of the file.

```
(r"H:\Ghostbusters.1984.REPACK.2160p.BluRay.REMUX.DV.HDR.HEVC.TrueHD.7.1.Atmos-BLURANiUM.mkv", "BLURANiUM", Resize(1920, 1080), DOVI)
```

Resizes the BLURANiUM remux to 1920x1080 and applies Dolby Vision tonemapping.

```python
((r"H:\XANADU_MAGICAL_MUSIC_EDITION\VIDEO_TS\VTS_01_1.VOB",
  r"H:\XANADU_MAGICAL_MUSIC_EDITION\VIDEO_TS\VTS_01_2.VOB",
  r"H:\XANADU_MAGICAL_MUSIC_EDITION\VIDEO_TS\VTS_01_3.VOB",
  r"H:\XANADU_MAGICAL_MUSIC_EDITION\VIDEO_TS\VTS_01_4.VOB",
  r"H:\XANADU_MAGICAL_MUSIC_EDITION\VIDEO_TS\VTS_01_5.VOB"),
  "USA NTSC DVD", NoFPS)
```

The above example combines the 5 VOB files from the Xanadu DVD and skips FPS normalization.
