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
