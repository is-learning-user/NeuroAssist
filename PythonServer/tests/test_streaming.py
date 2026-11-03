import numpy as np
from sklearn.linear_model import LogisticRegression
from neuroassist.features import spectral_features
from neuroassist.streaming import event_for_window

def test_prediction_is_computed_from_eeg_window():
    fs=128
    t=np.arange(512)/fs
    a=np.vstack([np.sin(2*np.pi*10*t)]*19)
    b=np.vstack([np.sin(2*np.pi*21*t)]*19)
    x=np.vstack([spectral_features(a,fs),spectral_features(b,fs)])
    model=LogisticRegression().fit(np.repeat(x,2,axis=0),[0,0,1,1])
    artifact={'model':model}
    evt=event_for_window(artifact,b,fs,0,'recording.edf')
    assert evt['type']=='prediction' and 0<=evt['p_task']<=1
    assert evt['source']=='recording.edf' and 'NOT' in evt['meaning']
