This is a collection of 1-file python/batch scripts for making life easier when creating P2P releases.

# Quick Links
- [General Scripts](#general-scripts)
- [Subtitle Scripts](#subtitle-scripts)
- [Audio Scripts](#audio-scripts)
- [Video Scripts](#video-scripts)

# General Scripts
<h2><a href="https://github.com/9Oc/Squash-P2P-Script-Emporium/blob/main/general/globaltags.py">globaltags</a>
<a href="https://www.python.org/downloads/release/python-3100/"><img src="https://img.shields.io/badge/Python-3.10%2B-brightgreen" alt="Python 3.10+"></a></h2>

`globaltags.py` generates an mkv XML tag file containing the TMDB, IMDB, and TVDB2 IDs for a given TMDB ID.

Dependencies:

`pip install tvdb_v4_official requests rich`

Note that you must provide your TMDB and TVDB API keys at the top of the script.
```
TMDB_API_KEY = "TMDB_API_KEY" # <-- your TMDB api key here
TVDB_API_KEY = "TVDB_API_KEY" # <-- your TVDB api key here
```

<hr>

### Usage
A TMDB ID is the only argument accepted.

`globaltags.py <TMDB ID>`
<hr>
Example output:

```
globaltags.py 9005
Fetching data for TMDB ID: 9005

TMDB match: The Ice Harvest (2005)
TMDB ID: 9005
TMDB URL: https://www.themoviedb.org/movie/9005

IMDB ID: tt0400525
IMDB URL: https://www.imdb.com/title/tt0400525

TVDB match: The Ice Harvest (2005)
TVDB ID: 8208
TVDB URL: https://www.thetvdb.com/movies/the-ice-harvest

XML file saved as: .global_tags_The Ice Harvest_2005.xml

<?xml version="1.0" encoding="UTF-8"?>
<Tags>
  <Tag>
    <Simple>
      <Name>TMDB</Name>
      <String>movie/9005</String>
    </Simple>
    <Simple>
      <Name>IMDB</Name>
      <String>tt0400525</String>
    </Simple>
    <Simple>
      <Name>TVDB2</Name>
      <String>movies/8208</String>
    </Simple>
  </Tag>
</Tags>
```

# Subtitle Scripts
<h2><a href="https://github.com/9Oc/Squash-P2P-Script-Emporium/blob/main/subtitles/supmapper.py">supmapper</a>
<a href="https://www.python.org/downloads/release/python-3100/"><img src="https://img.shields.io/badge/Python-3.10%2B-brightgreen" alt="Python 3.10+"></a></h2>

`supmapper.py` is an automatic PGS subtitle tonemapper. It will tonemap a directory (or multiple directories) of .sup files to match the brightness of a reference .sup file.

Dependencies:

`pip install git+https://github.com/cubicibo/SUPer.git`

[SupMover](https://github.com/MonoS/SupMover) must be in your PATH with the .exe named `SupMover.exe`.
<hr>

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

<h2><a href="https://github.com/9Oc/Squash-P2P-Script-Emporium/blob/main/subtitles/suppf.py">suppf</a>
<a href="https://www.python.org/downloads/release/python-360/"><img src="https://img.shields.io/badge/Python-3.06%2B-brightgreen" alt="Python 3.06+"></a></h2>

`suppf.py` is PGS subtitle palette fixer that corrects common subtitle color issues.

Dependencies: None
<hr>

### Usage
Supplying only an input and output defaults to using automatic detection for what color(s) to fix.

`suppf.py input.sup output.sup`

Supplying a main color signals to the script that this is the color meant to be fixed.

`suppf.py input.sup output.sup --main-color yellow`

`suppf.py input.sup output.sup --main-color blue`

`suppf.py input.sup output.sup --main-color a7a792`

Appending the quiet argument suppresses verbose output.

`append --quiet for no debug output`
<hr>
Example of a bad PGS subtitle being fixed by the script

Input .sup

<img src="https://img.onlyimage.org/8qfPAc.png" width="517" height="393">

Fixed .sup with suppf

<img src="https://img.onlyimage.org/8qfLnZ.png" width="517" height="393">


# Audio Scripts
<h2><a href="https://github.com/9Oc/Squash-P2P-Script-Emporium/blob/main/audio/gen_waveforms.py">gen_waveforms</a>
<a href="https://www.python.org/downloads/release/python-3100/"><img src="https://img.shields.io/badge/Python-3.10%2B-brightgreen" alt="Python 3.10+"></a></h2>

`gen_waveforms.py` will create a png image representing the waveforms of a given FLAC/WAV audio file with clipping highlighted.

Dependencies:

`pip install soundfile numpy matplotlib`
<hr>

### Usage
An input and an output path are required arguments.

`gen_waveforms.py -i input.flac -o input_waveforms.png`
<hr>

### Example Output
<img src="https://img.onlyimage.org/FtvQN6.png" width="425" height="300">

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
