"""Finite, per-window frequency-domain EEG features."""
import numpy as np
from scipy.signal import welch, detrend

BANDS = {'theta':(4,8), 'alpha':(8,13), 'beta':(13,30)}


def spectral_features(window: np.ndarray, sfreq: float) -> np.ndarray:
    """Band power / total 4..30 Hz per channel, logs, + theta/beta ratio.

    No global normalization: each window processed independently.
    Preprocessed EEGMAT already has upstream filtering / artifact cleaning.
    """
    if window.ndim != 2 or window.shape[0] < 1 or window.shape[1] < sfreq * 2:
        raise ValueError('EEG window must have >= 2 seconds and shape channels x samples')
    if not np.isfinite(window).all():
        raise ValueError('Invalid EEG samples')
    cleaned = detrend(window, axis=1, type='constant')
    f, pxx = welch(cleaned, fs=sfreq, nperseg=min(int(sfreq*2),window.shape[1]), axis=1)
    eps = 1e-25
    total_mask = (f >= 4) & (f < 30)
    total = np.trapezoid(pxx[:,total_mask], f[total_mask],axis=1) + eps
    bands = []
    for low,high in BANDS.values():
        mask = (f>=low) & (f<high)
        power = np.trapezoid(pxx[:,mask], f[mask],axis=1) + eps
        bands.append(power)
    features = [np.log10(np.maximum(power,eps)) for power in bands]
    features.extend([power/total for power in bands])
    features.append(np.log10(bands[0]/bands[2]))
    vec = np.concatenate(features).astype(np.float64)
    if not np.isfinite(vec).all():
        raise ValueError('Non-finite EEG features')
    return vec
