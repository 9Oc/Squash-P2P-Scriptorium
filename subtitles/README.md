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

<h2><a href="https://github.com/9Oc/Squash-P2P-Script-Emporium/blob/main/subtitles/syncsubs.py">syncsubs</a>
<a href="https://www.python.org/downloads/release/python-360/"><img src="https://img.shields.io/badge/Python-3.06%2B-brightgreen" alt="Python 3.06+"></a></h2>

`syncsubs.py` will sync a given directory containing .srt subtitle files to a given audio file.

Dependencies:

`pip install ffsubsync`

[ffmpeg](https://www.ffmpeg.org/download.html) must be installed and in your PATH.
<hr>

### Usage
The only required argument is a path to a folder containing the .srt files you want to sync. When no audio file is provided, the script will search for an audio file to sync to in the parent directory of the subtitles folder.

`syncsubs.py "path\to\subtitles"`

Optionally, provide a specific audio file to sync to. The audio file can be any codec.

`syncsubs.py "path\to\subtitles" --audio "path\to\audio.flac"`

By default, the script processes `N` number of subtitles concurrently where `N` is the number of threads your CPU has. To adjust how many subtitles are processed at once, provide a number of max workers. It may be beneficial to lower the number of max workers if you are syncing many subtitle files and do not have a high thread count CPU.

`syncsubs.py "path\to\subtitles" --audio "path\to\audio.flac" --max-workers 5`

<h2><a href="https://github.com/9Oc/Squash-P2P-Script-Emporium/blob/main/subtitles/syncsups.py">syncsups</a>
<a href="https://www.python.org/downloads/release/python-3100/"><img src="https://img.shields.io/badge/Python-3.10%2B-brightgreen" alt="Python 3.10+"></a></h2>

`syncsups.py` will sync a given directory containing PGS .sup subtitle files to a given audio file.

Note that this script will work on any PGS .sup file which has the standard 2 Display Sets per epoch as well as an additional non-standard type which contains `N` Display Sets per epoch. There may be additional non-standard Display Set structures which the script cannot parse properly. If you come across a PGS .sup file that the script fails to sync due to improper parsing of timestamps, please create a <a href="https://github.com/9Oc/Squash-P2P-Script-Emporium/issues">github issue</a> with a link to the PGS .sup file.

Dependencies:

`pip install ffsubsync git+https://github.com/cubicibo/SUPer.git`

[ffmpeg](https://www.ffmpeg.org/download.html) must be installed and in your PATH.
<hr>

### Usage
The only required argument is a path to a folder containing the PGS .sup files you want to sync. When no audio file is provided, the script will search for an audio file to sync to in the parent directory of the subtitles folder.

`syncsups.py "path\to\subtitles"`

Optionally, provide a specific audio file to sync to. The audio file can be any codec.

`syncsups.py "path\to\subtitles" --audio "path\to\audio.flac"`

By default, the script processes `N` number of subtitles concurrently where `N` is the number of threads your CPU has. To adjust how many subtitles are processed at once, provide a number of max workers. It may be beneficial to lower the number of max workers if you are syncing many subtitle files and do not have a high thread count CPU.

`syncsubs.py "path\to\subtitles" --audio "path\to\audio.flac" --max-workers 5`

Optionally, provide the `--keep-temp` argument to keep the temporary dummy .srt files created which the script generates and uses to write the new timestamps and framerate to the synced .sup files. This argument can be omitted in a majority of cases and is only used for debugging purposes.

`syncsups.py "path\to\subtitles" --keep-temp`
