"""Write limited-purpose EDF fixtures for IO tests only. Never use for scientific metrics."""
from pathlib import Path
import numpy as np
from neuroassist.dataset import ELECTRODES


def _field(value,width):
    s=str(value)
    if len(s)>width:raise ValueError(s)
    return s.ljust(width).encode('ascii')


def write_edf(path, signals, fs=100):
    """EDF test file; each second one record. Physical unit microvolt."""
    path=Path(path)
    names=[f'EEG {ch}' for ch in ELECTRODES]+['ECG','EOG']
    ns=len(names)
    nseconds=signals.shape[1]//fs
    assert signals.shape == (ns,nseconds*fs)
    hdr=b''.join([
      _field('0',8),_field('Synthetic test',80),_field('Test-only',80),
      _field('01.01.01',8),_field('01.01.01',8),_field(256+ns*256,8),
      _field('',44),_field(nseconds,8),_field('1',8),_field(ns,4),
    ])
    attrs=[('names',16,names),('transducer',80,['']*ns),('unit',8,['uV']*ns),
           ('pmin',8,['-200']*ns),('pmax',8,['200']*ns),('dmin',8,['-32768']*ns),
           ('dmax',8,['32767']*ns),('prefilter',80,['']*ns),('n_samples',8,[str(fs)]*ns),
           ('reserved',32,['']*ns)]
    for _, width, vals in attrs:
        hdr+=b''.join(_field(v,width) for v in vals)
    assert len(hdr)==256+ns*256
    with path.open('wb') as h:
        h.write(hdr)
        for second in range(nseconds):
            for ch in range(ns):
                uV=np.clip(signals[ch,second*fs:(second+1)*fs],-200,200)
                dig=np.round(((uV+200)/400)*65535-32768).astype('<i2')
                h.write(dig.tobytes())


def generate_fixture(data_dir:Path, nsubjects=8, fs=100, seconds=12):
    data_dir=Path(data_dir);data_dir.mkdir(parents=True,exist_ok=True)
    for subject in range(nsubjects):
        rng=np.random.default_rng(1000+subject)
        t=np.arange(fs*seconds)/fs
        for condition in (1,2):
            waves=[]
            for channel in range(len(ELECTRODES)+2):
                alpha_amp=12 if condition==1 else 2
                beta_amp=2 if condition==1 else 12
                # small subject-to-subject variations
                v=alpha_amp*np.sin(2*np.pi*10*t+channel*.1)+beta_amp*np.sin(2*np.pi*20*t+channel*.3)
                v+=rng.normal(0,3,len(t))
                waves.append(v)
            write_edf(data_dir/f'Subject{subject:02d}_{condition}.edf',np.array(waves),fs=fs)
