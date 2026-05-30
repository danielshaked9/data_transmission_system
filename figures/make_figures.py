#!/usr/bin/env python3
"""Generate the chirp-communication figures used in the README.

Produces three PNGs that illustrate, with physically faithful signals:
  1. chirp_symbols.png   - LoRa symbols are cyclic frequency shifts of a chirp
  2. processing_gain.png - de-chirp + FFT recovers a signal below the noise floor
  3. sf_tradeoff.png     - spreading factor trades data rate for sensitivity/range

Run:  python figures/make_figures.py
"""
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = os.path.dirname(os.path.abspath(__file__))
INK, ACCENT, ACCENT2 = "#1C2833", "#1EA7A1", "#124C78"
plt.rcParams.update({
    "font.size": 10, "axes.edgecolor": "#5B6770", "axes.labelcolor": INK,
    "text.color": INK, "xtick.color": INK, "ytick.color": INK,
    "axes.titleweight": "bold",
    "figure.facecolor": "white", "axes.facecolor": "white",
})

# ---- Shared LoRa-style chirp parameters -------------------------------------
BW = 125e3            # bandwidth (Hz)
SF = 8                # spreading factor (small so chirps are easy to see)
M = 2 ** SF           # samples per symbol / number of distinct symbols
fs = BW               # one sample per chip
t = np.arange(M) / fs # one symbol duration


def base_chirp(down=False, m=M):
    """Base up-chirp (or down-chirp): instantaneous freq sweeps across BW."""
    tt = np.arange(m) / fs
    T = m / fs
    k = BW / T                             # sweep rate (Hz/s)
    f0 = -BW / 2
    phase = 2 * np.pi * (f0 * tt + 0.5 * k * tt**2)
    if down:
        phase = -phase
    return np.exp(1j * phase)


def lora_symbol(sym, m=M):
    """LoRa symbol `sym`: the base up-chirp shifted up by `sym` frequency bins.

    A frequency shift (multiply by a complex exponential) is the true LoRa
    encoding: de-chirping it against the conjugate base chirp leaves a pure
    tone exp(j 2 pi sym n / M), whose FFT is a single bin at `sym`. The sweep
    wraps modulo BW, giving the characteristic discontinuity in the spectrogram.
    """
    n = np.arange(m)
    return base_chirp(m=m) * np.exp(1j * 2 * np.pi * sym * n / m)


# =============================================================================
# Figure 1 — chirp symbols as cyclic shifts (spectrograms)
# =============================================================================
def fig_chirp_symbols():
    m = 4096                                   # dense symbol -> high-res sweep
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    for ax, sym, title in (
        (axes[0], 0, "Base up-chirp  (symbol 0)"),
        (axes[1], m // 3, f"Frequency shift  (symbol {m//3})"),
    ):
        sig = lora_symbol(sym, m=m)
        ax.specgram(sig, NFFT=256, Fs=fs, noverlap=248, cmap="magma")
        ax.set_title(title)
        ax.set_xlabel("time")
        ax.set_ylabel("frequency")
        ax.set_yticks([]); ax.set_xticks([])
    fig.suptitle("LoRa encodes data as cyclic shifts of a linear chirp",
                 fontweight="bold")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "chirp_symbols.png"), dpi=220,
                bbox_inches="tight")
    plt.close(fig)


# =============================================================================
# Figure 2 — processing gain: de-chirp + FFT pulls signal out of the noise
# =============================================================================
def fig_processing_gain():
    rng = np.random.default_rng(0)
    m = 1024                                  # SF=10 -> 30 dB processing gain
    sym = 360                                 # the transmitted symbol
    clean = lora_symbol(sym, m=m)

    # Add heavy noise so the chirp sits *below* the noise floor (SNR < 0 dB).
    snr_db = -12
    sig_p = np.mean(np.abs(clean) ** 2)
    noise_p = sig_p / (10 ** (snr_db / 10))
    noise = np.sqrt(noise_p / 2) * (rng.standard_normal(m) + 1j * rng.standard_normal(m))
    rx = clean + noise

    # De-chirp: multiply by conjugate base chirp, then FFT -> energy in one bin.
    dechirped = rx * np.conj(base_chirp(m=m))
    spec = np.abs(np.fft.fft(dechirped)) ** 2
    spec_db = 10 * np.log10(spec / spec.max() + 1e-12)
    bins = np.arange(m)

    # Raw received spectrum (no de-chirp) for comparison: energy smeared out.
    raw = np.abs(np.fft.fftshift(np.fft.fft(rx))) ** 2
    raw_db = 10 * np.log10(raw / raw.max() + 1e-12)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.0))
    axes[0].plot(np.linspace(-BW/2, BW/2, m) / 1e3, raw_db, color=ACCENT2, lw=0.5)
    axes[0].set_title("Received signal spectrum\n(chirp buried in noise, SNR = -12 dB)")
    axes[0].set_xlabel("frequency (kHz)")
    axes[0].set_ylabel("power (dB)")
    axes[0].set_ylim(-40, 2)

    axes[1].plot(bins, spec_db, color=ACCENT, lw=0.5)
    peak = int(np.argmax(spec))
    axes[1].axvline(peak, color="#C0392B", lw=1.0, ls="--")
    axes[1].annotate(f"symbol = {peak}", xy=(peak, 0),
                     xytext=(peak + 90, -8), color="#C0392B",
                     arrowprops=dict(arrowstyle="->", color="#C0392B"))
    axes[1].set_title("After de-chirp + FFT\n(all energy collapses into one bin)")
    axes[1].set_xlabel("FFT bin  (= symbol value)")
    axes[1].set_ylabel("power (dB)")
    axes[1].set_ylim(-40, 4)

    fig.suptitle("Processing gain: correlation recovers a signal below the noise floor",
                 fontweight="bold")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "processing_gain.png"), dpi=220,
                bbox_inches="tight")
    plt.close(fig)


# =============================================================================
# Figure 3 — spreading factor trades data rate for sensitivity (range)
# =============================================================================
def fig_sf_tradeoff():
    sf = np.arange(7, 13)
    bw = 125e3
    cr = 4 / 5                                   # coding rate 4/5
    # Raw LoRa bit rate:  Rb = SF * (BW / 2^SF) * CR
    rb = sf * (bw / 2.0 ** sf) * cr              # bits/s
    # Receiver sensitivity per SF (typical SX127x, BW=125 kHz), more negative = better.
    sens = np.array([-123, -126, -129, -132, -133, -136.0])

    fig, ax1 = plt.subplots(figsize=(8.6, 4.2))
    c1, c2 = ACCENT2, ACCENT
    ax1.plot(sf, rb, "o-", color=c1, lw=2, label="data rate")
    ax1.set_xlabel("spreading factor (SF)")
    ax1.set_ylabel("data rate (bit/s)", color=c1)
    ax1.tick_params(axis="y", labelcolor=c1)
    ax1.set_yscale("log")

    ax2 = ax1.twinx()
    ax2.plot(sf, sens, "s--", color=c2, lw=2, label="sensitivity")
    ax2.set_ylabel("receiver sensitivity (dBm)  ← better / longer range",
                   color=c2)
    ax2.tick_params(axis="y", labelcolor=c2)
    ax2.invert_yaxis()                           # better sensitivity upward

    ax1.set_title("Higher SF = longer range, lower data rate", fontweight="bold")
    ax1.set_xticks(sf)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "sf_tradeoff.png"), dpi=220,
                bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    fig_chirp_symbols()
    fig_processing_gain()
    fig_sf_tradeoff()
    print("wrote: chirp_symbols.png, processing_gain.png, sf_tradeoff.png")
