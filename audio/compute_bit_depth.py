"""
Plots the average bit-depth of a FLAC/WAV audio file.

Dependencies:
pip install soundfile numpy matplotlib
"""
import soundfile as sf
import numpy as np
import matplotlib.pyplot as plt
import argparse
import os

def main():
    # parse arguments
    parser = argparse.ArgumentParser(description='Analyze bit depth of an audio file over time')
    parser.add_argument('-i', '--input', required=True, help='Input audio file path')
    parser.add_argument('-w', '--window', type=float, default=0.5, 
                       help='Window duration in seconds (default: 0.5)')
    
    args = parser.parse_args()
    file_name = os.path.basename(args.input)
    
    # load audio into soundfile
    data, samplerate = sf.read(args.input, dtype='float32', always_2d=True)
    
    # soundfile parameters
    window_duration = args.window
    window_size = int(window_duration * samplerate)
    step_size = window_size
    num_windows = (len(data) - window_size) // step_size
    min_bits = []
    max_bits = []
    avg_bits = []
    times = []
    
    # average channels to mono
    if data.ndim > 1:
        data = data.mean(axis=1)
    
    # normalize data in float [-1, 1]
    scaled_data = (data * (2**23)).astype(np.int32)
    
    for i in range(0, len(scaled_data) - window_size, step_size):
        window = scaled_data[i:i+window_size]
        abs_vals = np.abs(window)
        nonzero = abs_vals[abs_vals > 0]
        if nonzero.size == 0:
            min_b = max_b = avg_b = 0
        else:
            bits_used = np.floor(np.log2(nonzero)).astype(int) + 1
            min_b = bits_used.min()
            max_b = bits_used.max()
            avg_b = bits_used.mean()
        min_bits.append(min_b)
        max_bits.append(max_b)
        avg_bits.append(avg_b)
        times.append(i / samplerate)
        
    overall_avg = np.mean(avg_bits)
    overall_max = np.max(max_bits)
    
    # plot
    plt.figure(figsize=(12, 6))
    plt.plot(times, min_bits, label="Min Bits Used", linewidth=0.5)
    plt.plot(times, max_bits, label="Max Bits Used", linewidth=0.5)
    plt.plot(times, avg_bits, label="Avg Bits Used", linewidth=0.5)
    plt.xlabel("Time (s)")
    plt.ylabel("Effective Bit Depth")
    plt.title(f"{file_name}\n"
		f"Effective Bit Usage Over Time (Per {window_duration:.2f}s Window)\n"
        f"Overall Avg: {overall_avg:.2f} bits   Max: {overall_max:.0f} bits")
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    main()
