from pathlib import Path
import numpy as np
import pytest
from sklearn.model_selection import GroupShuffleSplit
from neuroassist.dataset import canonical_channel,discover,read_eeg,comparable_windows
from neuroassist.features import spectral_features
from neuroassist.benchmark import run_benchmark,build_arrays
from tests.make_fixture import generate_fixture


def test_labels_and_pairing(tmp_path):
    generate_fixture(tmp_path,nsubjects=2)
    x=discover(tmp_path)
    assert set(x)=={'00','01'}
    assert x['00'][1].name=='Subject00_1.edf'
    assert x['00'][2].name=='Subject00_2.edf'
    assert canonical_channel('EEG Fp1-Ref')=='Fp1'
    assert canonical_channel('ECG') is None


def test_reader_edf_and_features(tmp_path):
    generate_fixture(tmp_path,nsubjects=1)
    x,fs,meta=read_eeg(tmp_path/'Subject00_2.edf')
    assert x.shape==(19,1200)
    assert fs==100 and abs(meta['duration_s']-12)<1e-3
    feat=spectral_features(x[:,:400],fs)
    assert feat.shape==(19*7,)
    assert np.isfinite(feat).all()
    assert len(list(comparable_windows(tmp_path,window_s=4,max_s=12)))==6


def test_train_split_no_leak_and_metrics(tmp_path):
    generate_fixture(tmp_path/'fixture',nsubjects=8)
    X,y,g,_=build_arrays(tmp_path/'fixture',window_s=4,max_s=12)
    assert X.shape[0]==48 and len(np.unique(g))==8
    train,test=next(GroupShuffleSplit(n_splits=1,test_size=.25,random_state=42).split(X,y,g))
    assert set(g[train]).isdisjoint(set(g[test]))
    report=run_benchmark(tmp_path/'fixture',tmp_path/'outputs',window_s=4,max_s=12)
    assert (tmp_path/'outputs'/'model.joblib').exists()
    assert (tmp_path/'outputs'/'report.json').exists()
    assert report['subjects']==8
    assert set(report['train_subjects']).isdisjoint(report['test_subjects'])
    assert 0<=report['models']['logistic']['session_level']['balanced_accuracy']<=1


def test_missing_pair_fails(tmp_path):
    generate_fixture(tmp_path,nsubjects=1)
    (tmp_path/'Subject00_2.edf').unlink()
    with pytest.raises(ValueError,match='парных'):
        discover(tmp_path)
