"""Subject-specific rest calibration, evaluated on *later* rest windows and task windows.
Training/validation subjects never mix. Calibration is an explicit 12-second eyes-closed rest protocol.
"""
import json,time
from pathlib import Path
import numpy as np
from sklearn.model_selection import GroupShuffleSplit,GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.svm import SVC
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import balanced_accuracy_score
from neuroassist.dataset import comparable_windows
from neuroassist.features import spectral_features
from neuroassist.benchmark import metric_set
from scripts.improve_model import enhanced_features

def dataset(base):
    # two sets of features and calibration; each window from 4s; first 12 sec rest reserved for calibration
    rows={}
    for item in comparable_windows(base):
        sid=item['subject']; label=item['label']; off=item['offset_s']
        k=(sid,label)
        rows.setdefault(k,[]).append((off,spectral_features(item['window'],item['sfreq']), enhanced_features(item['window'],item['sfreq'])))
    xsets={'original':[],'enhanced':[],'original_delta':[],'enhanced_delta':[], 'enhanced_logratio':[]}
    ys=[]; groups=[]; keys=[]
    for sid in sorted({k[0] for k in rows}):
        ref=rows[(sid,0)]
        cal0=np.mean([r[1] for r in ref if r[0]<12],axis=0)
        cal1=np.mean([r[2] for r in ref if r[0]<12],axis=0)
        for label in [0,1]:
            for off,ft0,ft1 in rows[(sid,label)]:
                if label==0 and off<12:continue
                for n,v in [('original',ft0),('enhanced',ft1),('original_delta',ft0-cal0),('enhanced_delta',ft1-cal1),('enhanced_logratio',np.sign(ft1-cal1)*np.log1p(np.abs(ft1-cal1)))]: xsets[n].append(v)
                ys.append(label);groups.append(sid);keys.append((sid,label))
    return {k:np.asarray(v) for k,v in xsets.items()},np.asarray(ys),np.asarray(groups),keys

def main():
    t=time.time()
    X,y,g,keys=dataset(Path('data/eegmat_nemar'))
    tr,te=next(GroupShuffleSplit(n_splits=1,test_size=.25,random_state=42).split(X['original'],y,g))
    assert sorted(set(g[te]))==['08','12','13','16','21','26','30','31','35']
    folds=list(GroupKFold(n_splits=5).split(X['original'][tr],y[tr],g[tr]))
    methods={
       'logistic':lambda:make_pipeline(StandardScaler(),LogisticRegression(C=.1,max_iter=1500)),
       'svm_linear':lambda:make_pipeline(StandardScaler(),SVC(kernel='linear',C=.1)),
       'svm_rbf':lambda:make_pipeline(StandardScaler(),SVC(kernel='rbf',C=1)),
       'random_forest':lambda:RandomForestClassifier(n_estimators=150,min_samples_leaf=3,n_jobs=-1,random_state=42)
    }
    rows=[]
    for name,x in X.items():
        for modelname,factory in methods.items():
            scores=[]
            for a,b in folds:
                m=factory();m.fit(x[tr[a]],y[tr[a]])
                scores.append(balanced_accuracy_score(y[tr[b]],m.predict(x[tr[b]])))
            rows.append(dict(features=name,model=modelname,mean=float(np.mean(scores)),scores=[float(s) for s in scores]))
            print(name,modelname,round(np.mean(scores),4),flush=True)
    rows.sort(key=lambda d:d['mean'],reverse=True)
    best=rows[0]
    model=methods[best['model']]();model.fit(X[best['features']][tr],y[tr]); pred=model.predict(X[best['features']][te]);
    # one vote per session, only for reporting not model selection
    from collections import defaultdict
    vote=defaultdict(list)
    for idx,pr in zip(te,pred):vote[keys[idx]].append(int(pr))
    sess_y=np.asarray([k[1] for k in vote]);sess_pred=np.asarray([int(np.mean(a)>=.5) for a in vote.values()])
    report={'method':'12s rest calibration reserved; do not score calibration segments; only new participants in test', 'selected_on_train_cv':best,
     'top_cv':rows[:10], 'test_window':metric_set(y[te],pred),'test_session':metric_set(sess_y,sess_pred),
     'train_subjects':sorted(set(g[tr])),'test_subjects':sorted(set(g[te])),'timing_sec':time.time()-t,
     'limitations':['Calibration uses ground-truth rest period; no deployment without such a protocol.', 'Prior exploratory use of same held-out subjects means test score not an untouched confirmatory estimate.', 'Rest vs arithmetic is confounded by experimental conditions.']}
    folder=Path('outputs/calibration_experiment');folder.mkdir(exist_ok=True,parents=True)
    (folder/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))
    import joblib
    joblib.dump({'model':model,'feature_variant':best['features'],'calibration_seconds':12,'window_seconds':4,'training_subjects':report['train_subjects'],'calibration_protocol':'first 12s of separately identified baseline/rest EEG','task':'rest versus arithmetic'},folder/'model_calibrated.joblib')
    print('FINAL',json.dumps({'selected':best,'test':report['test_window'],'session':report['test_session']}),flush=True)
if __name__=='__main__':main()
