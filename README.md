This is a collection of 1-file python/batch scripts for making life easier when creating P2P releases.

# Quick Links
- [Subtitle Scripts](#subtitle-scripts)
- [Audio Scripts](#audio-scripts)
- [Video Scripts](#video-scripts)

# Subtitle Scripts
## supmapper
supmapper is an automatic PGS subtitle tonemapper. It will tonemap a directory (or multiple directories) of .sup files to match the brightness of a reference .sup file.

Requirements: Python 3.10+

Dependencies:

`pip install git+https://github.com/cubicibo/SUPer.git`

[SupMover](https://github.com/MonoS/SupMover) must be in your PATH with the .exe named `SupMover.exe`.

### Usage
An input directory (or multiple directories) and the tonemapping method are required arguments.

Using a reference file

`supmapper.py "/path/to/subtitles" --reference "/path/to/reference.sup"`
  
`supmapper.py "/path/to/subtitles" -r "/path/to/reference.sup"`
  
Using a target percentage
  
`supmapper.py "/path/to/subtitles" --percent 60.5`
  
`supmapper.py "/path/to/subtitles" -p 60.5`
  
Using a target RGB value
  
`supmapper.py "/path/to/subtitles" --rgb 180`

To provide multiple directories for input, simply add additional directories to the command

`supmapper.py "/path/to/subtitles1" "/path/to/subtitles2" "/path/to/subtitles3" --reference "/path/to/reference.sup"`

## suppf
suppf is PGS subtitle palette fixer that corrects common subtitle color issues.

Requirements: Python 3.6+

Dependencies: None

### Usage
Supplying only an input and output defaults to using automatic detection for what color(s) to fix.

`suppf.py input.sup output.sup`

Supplying a main color signals to the script that this is the color meant to be fixed.

`suppf.py input.sup output.sup --main-color yellow`

`suppf.py input.sup output.sup --main-color blue`

`suppf.py input.sup output.sup --main-color a7a792`

Appending the quiet argument suppresses verbose output.

`append --quiet for no debug output`


### Examples
Input .sup

<img src="https://img.onlyimage.org/8qfPAc.png" width="517" height="393">

Fixed .sup with suppf

<img src="https://img.onlyimage.org/8qfLnZ.png" width="517" height="393">


# Audio Scripts

## gen_waveforms
gen_waveforms will create a png image representing the waveforms of a given FLAC/WAV audio file with clipping highlighted.

Requirements: Python 3.10+

Dependencies:

`pip install soundfile numpy matplotlib`

### Usage
An input and an output path are required arguments.

`gen_waveforms.py -i input.flac -o input_waveforms.png`

### Example Output
<img src="https://img.onlyimage.org/FtvQN6.png" width="425" height="300">

# Video Scripts

## check_idr
check_idr will determine if a given frame in an h264 raw stream is an IDR frame or not.

Requirements: Python 3.7+

Dependencies:

`pip install rich`

[ffmpeg](https://www.ffmpeg.org/download.html) must be installed and in your PATH.

### Usage
A path to a raw h264 stream and a frame number are required arguments.

`check_idr.py video.h264 --frame 1000`

Adding the `--verbose` argument will output all IDR frames found up to the given frame number.

### Example
<img src="https://img.onlyimage.org/FtXJGy.png">
