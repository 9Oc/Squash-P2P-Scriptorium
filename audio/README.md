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
<hr>

<h2><a href="https://github.com/9Oc/Squash-P2P-Script-Emporium/blob/main/audio/gen_spectrograms.bat">gen_spectrograms</a></h2>

`gen_spectrograms.bat` generates spectrogram images for any `.flac` audio files in the given directory.

Dependencies:

<a href="https://github.com/chirlu/sox">SoX</a> must be in your PATH.
<hr>

### Usage
Double click `gen_spectrograms.bat` and enter the directory containing the `.flac` files you want to generate spectrograms for. The script will recursively search through sub-folders inside the given directory so spectrograms will be generated for any `.flac` files immediately inside the given directory and any `.flac` files inside sub-folders of the given directory.

<h2><a href="https://github.com/9Oc/Squash-P2P-Script-Emporium/blob/main/audio/compute_bit_depth.py">compute_bit_depth</a>
<a href="https://www.python.org/downloads/release/python-380/"><img src="https://img.shields.io/badge/Python-3.08%2B-brightgreen" alt="Python 3.08+"></a></h2>

`compute_bit_depth.py` plots the average bit-depth of a FLAC/WAV audio file.

Dependencies:

`pip install soundfile numpy matplotlib`
<hr>

### Usage
A path to a FLAC/WAV audio file is the only required argument.

`compute_bit_depth.py -i "path\to\audio.flac"`

Optionally provide a float with `-w` to change the polling window. This value is in seconds and adjusts how frequently the audio file is polled for bit-depth. The default value is 0.5 seconds.

`compute_bit_depth.py -i "path\to\audio.flac" -w 1.0`
<hr>

Example output:
<img src="https://img.onlyimage.org/FC0B9Z.png">

<h2><a href="https://github.com/9Oc/Squash-P2P-Scriptorium/blob/main/audio/plotfreq.py">plotfreq</a>
<a href="https://www.python.org/downloads/release/python-390/"><img src="https://img.shields.io/badge/Python-3.09%2B-brightgreen" alt="Python 3.09+"></a></h2>

`plotfreq.py` plots the frequency response of each channel in a .flac or .wav audio file.

Dependencies:

`pip install soundfile numpy scipy matplotlib rich`

<a href="https://mediaarea.net/en/MediaInfo/Download">MediaInfo</a> must installed and `MediaInfo.exe` in your PATH.
<hr>

### Usage
A path to a FLAC/WAV audio file is the only required argument.

`plotfreq.py input.flac`

Optionally provide these arguments to your preferences:  
```
    --nperseg     Segment length for Welch (samples). Default: 65536
    --noverlap    Overlap between segments (samples). Default: nperseg//2
    --blocksize   Frames to read at once from disk. Default: 65536
    --window      Window name passed to scipy.signal.get_window. Default: 'hann'
    --out, -o     Output image file path. Default: <input>_freq_response.png
    --dpi         Output image DPI. Default: 140
    --figsize     Figure size in inches as "W,H". Default: "16,9"
    --linewidth   Line width for each channel trace. Default: 0.5
    --labels      Optional channel labels (provide one per channel). Default: automated channel label mapping.
```

Example output:  
<a href="https://img.onlyimage.org/Q9ypnG.webp"><img src="https://img.onlyimage.org/Q9ypnG.webp" width="668" height="373"></a>
