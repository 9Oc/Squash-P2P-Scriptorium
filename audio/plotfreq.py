#!/usr/bin/env python3
"""
plotfreq.py
Plots the frequency response of each channel in a .flac audio file (frequency (Hz) X power (dB))

Dependencies:
    pip install soundfile numpy scipy matplotlib rich
    Ensure MediaInfo is in your PATH with the executable named "MediaInfo.exe"
Usage:
    python plotfreq.py input.flac

Optional args:
    --nperseg     Segment length for Welch (samples). Default: 65536
    --noverlap    Overlap between segments (samples). Default: nperseg//2
    --blocksize   Frames to read at once from disk. Default: 65536
    --window      Window name passed to scipy.signal.get_window. Default: 'hann'
    --out, -o     Output image file path. Default: <input>_freq_response.png
    --dpi         Output image DPI. Default: 140
    --figsize     Figure size in inches as "W,H". Default: "16,9"
    --linewidth   Line width for each channel trace. Default: 0.5
    --labels      Optional channel labels (provide one per channel). Default: automated channel label mapping.
"""

import argparse
import contextlib
import os
import subprocess

from pathlib import Path

import numpy as np
import soundfile as sf
import matplotlib
# use non-interactive backend so script works on headless servers
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import LogLocator, FuncFormatter
from rich.console import Console
from scipy.signal import get_window

CHANNEL_LABEL_MAP = {
    "L": "Left",
    "R": "Right",
    "C": "Center",
    "M": "Center",
    "LFE": "LFE",
    "Rs": "Right Surround",
    "Ls": "Left Surround",
    "Lb": "Left Back Surround",
    "Rb": "Right Back Surround",
    "Cb": "Center Back",
    "Lss": "Left Side Surround",
    "Rss": "Right Side Surround",
}
CHANNEL_PALETTE_MAP = {
    "LFE": "#D32D2D",  # red
    "M": "#D32D2D",  # red
    "C": "#CFCFCF",  # white
    "L": "#ffa500",  # orange
    "R": "#487de7",  # blue
    "Rs": "#A23BA2",  # magenta
    "Ls": "#2DD32D",  # green
    "Lb": "#f4f30c",  # yellow
    "Rb": "#0C0DF4",  # blue
    "Cb": "#E30B5C",  # raspberry
    "Lss": "#bcf60c",  # lime
    "Rss": "#fabebe",  # light pink
}
DARK_GREY_HEX = "#141414"

console = Console(color_system="truecolor")

def analyze_file(file_path, nperseg=65536, noverlap=None, window="hann", blocksize=65536, verbose=True):
    if noverlap is None:
        noverlap = nperseg // 2
    if not (0 <= noverlap < nperseg):
        raise ValueError("noverlap must satisfy 0 <= noverlap < nperseg")

    step = nperseg - noverlap
    win = get_window(window, nperseg, fftbins=True).astype(np.float64)
    U = np.sum(win * win)  # window power normalization
    nfft = nperseg
    with sf.SoundFile(file_path, "r") as sfobj:
        fs = sfobj.samplerate
        n_channels = sfobj.channels
        freq = np.fft.rfftfreq(nfft, d=1.0 / fs)
        n_freq = freq.size

        sum_Pxx = np.zeros((n_channels, n_freq), dtype=np.float64)
        n_segments = 0
        buffer = np.empty((0, n_channels), dtype=np.float64)

        if verbose:
            print(f"File: {file_path.name}")
        
        step = nperseg - noverlap

        # try to read total_frames from the file object
        total_frames = getattr(sfobj, "frames", None)
        
        if total_frames is None:
            total_segments = None  # unknown (e.g. streaming input)
        else:
            total_frames = int(total_frames)
            if total_frames < nperseg:
                total_segments = 0
            else:
                total_segments = 1 + (total_frames - nperseg) // step
        status_ctx = console.status("Starting analysis...", spinner="dots") if verbose else contextlib.nullcontext()
        with status_ctx as status:
            while True:
                data = sfobj.read(frames=blocksize, always_2d=True, dtype='float64')
                if data.size == 0:
                    break
                buffer = np.vstack((buffer, data))
                while buffer.shape[0] >= nperseg:
                    segment = buffer[:nperseg, :]  # (nperseg, n_channels)
                    segment = segment - np.mean(segment, axis=0, keepdims=True)
                    xw = segment * win[:, None]
                    X = np.fft.rfft(xw, n=nfft, axis=0)  # (n_freq, n_channels)
                    periodogram = (np.abs(X) ** 2) / U  # (n_freq, n_channels)
                    sum_Pxx += periodogram.T  # (n_channels, n_freq)
                    n_segments += 1
                    buffer = buffer[step:, :]
                    if status is not None:
                        status.update(f"Segments analyzed: {n_segments}/{total_segments}")

        if n_segments == 0:
            raise RuntimeError("No segments were processed (file too short for chosen nperseg).")

        Pxx = sum_Pxx / n_segments  # (n_channels, n_freq)
        return freq, Pxx, fs

def plot_and_save(freq, Pxx, fs, audio_file, out_path, labels=None, title=None, dpi=140, figsize=(16,9), line_width=0.5):
    colors = plt.get_cmap("Set3").colors
    channel_layout = run_mediainfo("Audio;%ChannelLayout%", audio_file).split(" ")
    
    bins_per_octave = 72   # smaller = smoother
    fmin = 20.0
    fmax = fs / 2.0

    freq_b, Pxx_b = log_bin_psd(freq, Pxx, bins_per_octave=bins_per_octave, fmin=fmin, fmax=fmax, method="mean")
    
    if freq_b.size == 0 or Pxx_b.size == 0:
        # skip DC (freq==0) if present
        pos = freq > 0
        plot_freq = freq[pos]
        plot_Pxx = Pxx[:, pos]
    else:
        plot_freq = freq_b
        plot_Pxx = Pxx_b
        
    eps = 1e-20
    plot_Pxx_db = 10.0 * np.log10(plot_Pxx + eps)

    fig, ax = plt.subplots(figsize=figsize)
    # set dark background for figure and axes
    fig.patch.set_facecolor(DARK_GREY_HEX)
    ax.set_facecolor(DARK_GREY_HEX)

    for i, ch in enumerate(channel_layout):
        P = Pxx[i]
        P_db = 10.0 * np.log10(P + 1e-20)
        Pxx_b_db = 10.0 * np.log10(Pxx_b + 1e-20)
        label = CHANNEL_LABEL_MAP[ch.strip()]
        y = plot_Pxx_db[i]
        ax.semilogx(plot_freq, y, label=label, color=CHANNEL_PALETTE_MAP[ch], linewidth=line_width)
    
    # build Y axis ticks and make sure 0 dB is included
    ystep = 20
    ymin = -120
    ymax = 5
    yticks = list(np.arange(ymin, ymax + 1e-6, ystep))
    if 0 not in yticks and ymin < 0 < ymax:
        yticks.append(0)
        yticks = sorted(yticks)

    ax.set_xlim(20, fs / 2)
    ax.set_xlabel("Frequency (Hz)", color="white")
    ax.set_ylim(ymin, ymax)
    ax.set_yticks(yticks)
    ax.set_ylabel("Power (dB)", color="white")
    if title:
        ax.set_title(title, color="white")
    else:
        ax.set_title(f"Frequency Response ({audio_file.name})", color="white")

    major_locator = LogLocator(base=10.0, subs=(1.0, 2.0, 5.0), numticks=15)
    ax.xaxis.set_major_locator(major_locator)
    minor_locator = LogLocator(base=10.0, subs=np.arange(1.0, 10.0), numticks=50)
    ax.xaxis.set_minor_locator(minor_locator)
    
    def format_hz(x, pos):
        # avoid tiny floating rounding issues and format output
        if x >= 1000:
            return f"{int(x/1000)}k"
        else:
            return f"{int(round(x))}"

    ax.xaxis.set_major_formatter(FuncFormatter(format_hz))

    # grid and tick styling for dark background
    ax.grid(which="both", linestyle=":", linewidth=0.5, color="#444444")
    ax.tick_params(axis="x", colors="white")
    ax.tick_params(axis="y", colors="white")
    # legend styling
    leg = ax.legend(loc="best", facecolor="#222222", edgecolor="#444444")
    for text in leg.get_texts():
        text.set_color("white")

    plt.tight_layout()

    fig.savefig(str(out_path), dpi=dpi, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"Saved plot to: {out_path} (dpi={dpi}, size={figsize}, linewidth={line_width})")
    plt.close(fig)

def log_bin_psd(freq, Pxx, bins_per_octave=12, fmin=None, fmax=None, method="mean"):
    """
    Re-bin PSD (Pxx: n_channels x n_freq) onto logarithmic frequency bins.
    
    Args:
        freq: 1D array of FFT bin center freqs (Hz), length n_freq (may include 0 Hz)
        Pxx: 2D array shape (n_channels, n_freq) (power, linear units)
    Returns:
        f_centers (n_bins,), Pxx_binned (n_channels, n_bins)
    """
    # ensure arrays are numpy
    freq = np.asarray(freq)
    Pxx = np.asarray(Pxx)

    # pick fmin: must be > 0 for log bins
    if fmin is None:
        # choose the greater of 20 Hz or the smallest positive freq bin
        pos_freqs = freq[freq > 0]
        if pos_freqs.size == 0:
            raise ValueError("freq contains no positive frequencies; cannot log-bin")
        fmin = max(20.0, float(pos_freqs.min()))
    if fmax is None:
        fmax = float(freq.max())

    if fmin <= 0:
        raise ValueError("fmin must be > 0 for logarithmic bins")

    # number of octaves between fmin and fmax
    octaves = np.log2(fmax / fmin)
    n_bins = int(np.ceil(octaves * bins_per_octave))
    if n_bins <= 0:
        return np.array([]), np.empty((Pxx.shape[0], 0))

    # edges: fmin * 2^(k / bins_per_octave)
    edges = fmin * (2.0 ** (np.arange(0, n_bins + 1) / bins_per_octave))
    # ensure last edge not beyond fmax
    edges[-1] = fmax

    n_channels = Pxx.shape[0]
    Pxx_binned = np.full((n_channels, n_bins), np.nan, dtype=Pxx.dtype)
    f_centers = np.empty(n_bins, dtype=float)

    # use searchsorted since freq is sorted
    for i in range(n_bins):
        e1 = edges[i]
        e2 = edges[i + 1]
        f_centers[i] = np.sqrt(e1 * e2)  # geometric center
        left = np.searchsorted(freq, e1, side="left")
        right = np.searchsorted(freq, e2, side="left")  # exclusive
        if right <= left:
            # no FFT bins fall in this bin
            continue
        idx = slice(left, right)
        if method == "mean":
            Pxx_binned[:, i] = np.mean(Pxx[:, idx], axis=1)
        elif method == "median":
            Pxx_binned[:, i] = np.median(Pxx[:, idx], axis=1)
        else:
            raise ValueError("method must be 'mean' or 'median'")

    # drop bins with no data across all channels
    valid = ~np.all(np.isnan(Pxx_binned), axis=0)
    f_centers = f_centers[valid]
    Pxx_binned = Pxx_binned[:, valid]

    return f_centers, Pxx_binned

def parse_figsize(s):
    try:
        w,h = s.split(",")
        return (float(w), float(h))
    except Exception:
        raise argparse.ArgumentTypeError("figsize must be 'W,H' (e.g. 16,9)")

def run_mediainfo(inform_format, input_file):
    try:
        result = subprocess.run(
            ["MediaInfo.exe", f'--Inform={inform_format}', input_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False
        )
        return result.stdout.strip()
    except Exception as e:
        print(f"Failed to run MediaInfo: {e}")
        return ""

def main():
    p = argparse.ArgumentParser(description="Stream-read a .wav/.flac file and save per-channel PSD plot to a .png image.")
    p.add_argument("infile", type=Path, help="Input .wav/.flac file")
    p.add_argument("--nperseg", type=int, default=65536, help="Segment length (samples) for Welch")
    p.add_argument("--noverlap", type=int, default=None, help="Overlap between segments (samples). Default nperseg//2")
    p.add_argument("--blocksize", type=int, default=65536, help="Block size to read from file (frames)")
    p.add_argument("--window", default="hann", help="Window name (passed to scipy.signal.get_window)")
    p.add_argument("--out", "-o", type=str, default=None, help="Output image path (defaults to <infile>_freq_response.png)")
    p.add_argument("--dpi", type=int, default=140, help="Output image DPI")
    p.add_argument("--figsize", type=parse_figsize, default=(16,9), help="Figure size in inches as 'W,H' (default '16,9')")
    p.add_argument("--labels", nargs="+", default=None, help="Optional list of channel labels")
    p.add_argument("--quiet", action="store_true", help="Reduce printed output")
    p.add_argument("--linewidth", type=float, default=0.5, help="Line width for channel traces (default 0.5)")
    args = p.parse_args()

    infile = Path(args.infile)
    out_path = args.out
    if out_path is None:
        out_path = infile.with_name(f"{infile.stem.replace('audio_', '')}_freq_response.png")

    freq, Pxx, fs = analyze_file(
        infile,
        nperseg=args.nperseg,
        noverlap=args.noverlap,
        window=args.window,
        blocksize=args.blocksize,
        verbose=not args.quiet,
    )

    labels = args.labels

    plot_and_save(freq, Pxx, fs, infile, out_path, labels=labels, dpi=args.dpi, figsize=args.figsize, line_width=args.linewidth)

if __name__ == "__main__":
    main()
