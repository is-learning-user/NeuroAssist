"""EEGMAT EDF discovery/reading with explicit experimental labels.

The dataset is recordings before (_1) vs during (_2) arithmetic. This does
NOT provide a continuously measured cognitive-workload score.
"""
from pathlib import Path
import re
from collections import Counter
import numpy as np
import mne

ELECTRODES = (
    'Fp1', 'Fp2', 'F7', 'F3', 'Fz', 'F4', 'F8', 'T3', 'C3',
    'Cz', 'C4', 'T4', 'T5', 'P3', 'Pz', 'P4', 'T6', 'O1', 'O2',
)
FILE_RE = re.compile(r'^Subject(\d{2})_([12])\.edf$', re.IGNORECASE)
BIDS_RE = re.compile(r'^sub-(\d{2})_task-(rest|mentalArithmetic)_eeg\.edf$', re.IGNORECASE)

def discover(data_dir: Path, require_complete: bool = True) -> dict[str, dict[int, Path]]:
    data_dir = Path(data_dir)
    recordings = {}
    for path in sorted(data_dir.rglob('*.edf')):
        match = FILE_RE.match(path.name)
        if match:
            subject, condition = match.groups()
            condition = int(condition)
        else:
            bids = BIDS_RE.match(path.name)
            if not bids:
                continue
            subject, task = bids.groups()
            condition = 1 if task.casefold() == 'rest' else 2
        records = recordings.setdefault(subject, {})
        if condition in records:
            raise ValueError(f'Дублирующая запись: {subject}_{condition}')
        records[condition] = path
    if not recordings:
        raise FileNotFoundError(f'В {data_dir} нет SubjectXX_1.edf / SubjectXX_2.edf. См. README.')
    missing = {sid: [c for c in (1,2) if c not in files] for sid,files in recordings.items() if len(files) != 2}
    if missing and require_complete:
        raise ValueError(f'Не хватает парных записей: {missing}. Нужны оба состояния одного человека.')
    return {sid: f for sid,f in recordings.items() if len(f) == 2}


def canonical_channel(name: str) -> str | None:
    # EDFs may store EEG Fp1-A1, Fp1-Ref, or plain Fp1; reject EOG/ECG.
    if re.search(r'\b(ECG|EKG|EOG|EMG|STATUS|EVENT|ANNOT)', name, re.I):
        return None
    cleaned = re.sub(r'^\s*EEG\s*', '', name, flags=re.I).strip()
    cleaned = re.split(r'[-/\s]', cleaned, maxsplit=1)[0].casefold()
    for electrode in ELECTRODES:
        if cleaned == electrode.casefold():
            return electrode
    return None


def read_eeg(path: Path) -> tuple[np.ndarray, float, dict]:
    """Returns 19 canonical EEG channels in V, sample rate and metadata."""
    raw = mne.io.read_raw_edf(str(path), preload=False, verbose='ERROR')
    found = {}
    for original in raw.ch_names:
        canonical = canonical_channel(original)
        if canonical is not None:
            if canonical in found:
                raise ValueError(f'{path}: duplicate electrode {canonical}: {original}, {found[canonical]}')
            found[canonical] = original
    missing = [c for c in ELECTRODES if c not in found]
    if missing:
        raise ValueError(f'{path}: нужны каналы {missing}; найдено: {raw.ch_names}. Проверьте исходный EDF.')
    selected = [raw.ch_names.index(found[ch]) for ch in ELECTRODES]
    values = raw.get_data(picks=selected)  # shape channels x samples, volts
    sfreq = float(raw.info['sfreq'])
    if not np.isfinite(values).all() or sfreq <= 0:
        raise ValueError(f'{path}: EEG contains NaN/Inf or invalid sampling frequency')
    metadata = {'name': path.name, 'channels': list(ELECTRODES), 'source_names': [found[c] for c in ELECTRODES],
                'samples': int(values.shape[1]), 'sampling_rate_hz': sfreq, 'duration_s': float(values.shape[1]/sfreq)}
    return values, sfreq, metadata


def comparable_windows(data_dir: Path, window_s: float = 4.0, max_s: float = 60.0, 
                       stride_s: float | None = None):
    """Use equal-length portions per condition within each subject.

    The dataset's _1 may be longer than _2; we use the FIRST shared
    max_s seconds of each. Do not overlap windows in evaluation by default.
    """
    if window_s <= 0 or max_s < window_s:
        raise ValueError('window_s must be positive and max_s >= window_s')
    stride_s = window_s if stride_s is None else stride_s
    if stride_s < window_s:
        raise ValueError('For this benchmark overlapping windows are disabled to avoid dependence')
    files = discover(data_dir)
    for sid, paired in files.items():
        baseline, fs_0, meta_0 = read_eeg(paired[1])
        task, fs_1, meta_1 = read_eeg(paired[2])
        if abs(fs_0-fs_1) > 1e-6:
            raise ValueError(f'Subject {sid}: different sampling rates ({fs_0} vs {fs_1})')
        length_s = min(max_s, meta_0['duration_s'], meta_1['duration_s'])
        n_samples = int(round(window_s*fs_0))
        stride = int(round(stride_s*fs_0))
        available = int(length_s*fs_0)
        if available < n_samples:
            raise ValueError(f'Subject {sid}: recording too short: {length_s:.1f}s')
        for label, data in ((0,baseline),(1,task)):
            for start in range(0, available-n_samples+1, stride):
                yield {'subject': sid, 'label': label, 'window': data[:, start:start+n_samples],
                       'sfreq': fs_0, 'offset_s': start/fs_0, 'duration_s': length_s}


def describe_dataset(data_dir: Path) -> dict:
    files = discover(data_dir)
    subjects = []
    for sid, paired in files.items():
        _, fs0, a = read_eeg(paired[1]); _, fs1, b = read_eeg(paired[2])
        subjects.append({'subject': sid, 'rest': a, 'task': b})
    return {'dataset': 'EEGMAT NEMAR nm000109 v1.0.0 / original PhysioNet', 'subjects_with_pairs': len(subjects),
            'expected_full_subjects': 36, 'subjects': subjects}
