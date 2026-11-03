"""Predeclared subject-group CV model comparison; fixed original held-out participants.

DO NOT use held-out scores for choosing model. EEGMAT rest-vs-arithmetic is not
an independent ground truth measure of cognitive workload.
"""
import argparse, json, time
from pathlib import Path
import numpy as np
from scipy.signal import welch
from sklearn.model_selection import GroupShuffleSplit, GroupKFold
from sklearn.preprocessing import StandardScaler, RobustScaler
from sklearn.pipeline import make_pipeline
from sklearn.linear_model import LogisticRegression, RidgeClassifier
from sklearn.svm import SVC
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.metrics import balanced_accuracy_score, f1_score, confusion_matrix
import joblib
from neuroassist.benchmark import build_arrays, metric_set
from neuroassist.dataset import comparable_windows, ELECTRODES
from neuroassist.features import BANDS


def enhanced_features(window, fs):
    n = window.shape[-1]
    freq, spec = welch(window-window.mean(axis=-1, keepdims=True), fs=fs, nperseg=min(int(fs*2),n), axis=-1)
    ranges = ((1,4),(4,8),(8,13),(13,20),(20,30),(30,40),(4,13),(13,30))
    band=[]
    for lo,hi in ranges:
        mask=(freq>=lo)&(freq<hi)
        band.append(np.maximum(np.trapezoid(spec[:,mask],freq[mask],axis=1),1e-24))
    denom=sum(band[i] for i in range(1,6)) + 1e-24
    vals=[np.log10(x) for x in band[:6]]
    vals += [x/denom for x in band[1:6]]
    vals += [np.log10(band[1]/band[3]),np.log10(band[2]/band[4])]
    # pooled summaries are simple physiological descriptors, not learned from all subjects
    for x in band[:6]:
        vals.append(np.asarray([np.mean(np.log10(x)),np.std(np.log10(x))]))
    return np.concatenate(vals).astype('float64')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-dir',default='data/eegmat_nemar')
    parser.add_argument('--output-dir',default='outputs/nemar_improved')
    args=parser.parse_args()
    output=Path(args.output_dir); output.mkdir(parents=True,exist_ok=True)
    # Run EXACTLY the pre-existing train/test split (seed 42), with a separate fixed train-CV.
    original_x,y,groups,offsets=build_arrays(Path(args.data_dir))
    extra=[]
    for row in comparable_windows(Path(args.data_dir)):
        extra.append(enhanced_features(row['window'],row['sfreq']))
    extra=np.vstack(extra)
    if len(y)!=len(extra): raise ValueError('feature row mismatch')
    Xsets={'original':original_x,'enhanced':extra}
    tr,te=next(GroupShuffleSplit(n_splits=1,test_size=.25,random_state=42).split(original_x,y,groups))
    expected=['08','12','13','16','21','26','30','31','35']
    assert sorted(set(groups[te]))==expected, 'Original held-out subjects changed'
    splits=list(GroupKFold(n_splits=5).split(original_x[tr],y[tr],groups[tr]))
    candidates={
      'logistic_C0.1':lambda:make_pipeline(StandardScaler(),LogisticRegression(C=.1,max_iter=2000,class_weight='balanced')),
      'logistic_C1':lambda:make_pipeline(StandardScaler(),LogisticRegression(C=1,max_iter=2000,class_weight='balanced')),
      'svm_linear_C0.1':lambda:make_pipeline(StandardScaler(),SVC(kernel='linear',C=.1,class_weight='balanced',probability=True,random_state=42)),
      'svm_rbf_C0.1':lambda:make_pipeline(StandardScaler(),SVC(kernel='rbf',C=.1,class_weight='balanced',probability=True,random_state=42)),
      'svm_rbf_C1':lambda:make_pipeline(StandardScaler(),SVC(kernel='rbf',C=1,class_weight='balanced',probability=True,random_state=42)),
      'svm_rbf_C10':lambda:make_pipeline(StandardScaler(),SVC(kernel='rbf',C=10,class_weight='balanced',probability=True,random_state=42)),
      'shrinkage_LDA':lambda:make_pipeline(StandardScaler(),LinearDiscriminantAnalysis(solver='lsqr',shrinkage='auto')),
      'extra_trees':lambda:ExtraTreesClassifier(n_estimators=160,min_samples_leaf=4,n_jobs=-1,random_state=42,class_weight='balanced'),
      'random_forest':lambda:RandomForestClassifier(n_estimators=160,min_samples_leaf=3,n_jobs=-1,random_state=42,class_weight='balanced'),
    }
    leaderboard=[]; start=time.time()
    for feature_name,X in Xsets.items():
        for name,constructor in candidates.items():
            values=[]
            for a,b in splits:
                model=constructor();model.fit(X[tr[a]],y[tr[a]])
                values.append(float(balanced_accuracy_score(y[tr[b]],model.predict(X[tr[b]]))))
            item={'features':feature_name,'model':name,'cv_balanced_accuracy_mean':float(np.mean(values)),
                  'cv_balanced_accuracy_sd':float(np.std(values)),'cv_fold_scores':values}
            leaderboard.append(item)
            print(f'{feature_name:9s} {name:20s} CV {item["cv_balanced_accuracy_mean"]:.4f}',flush=True)
    leaderboard.sort(key=lambda x:x['cv_balanced_accuracy_mean'],reverse=True)
    best=leaderboard[0]
    winning=candidates[best['model']](); winning.fit(Xsets[best['features']][tr],y[tr]); prediction=winning.predict(Xsets[best['features']][te])
    original_report=json.loads(Path('outputs/nemar_real/report.json').read_text())
    existing=original_report['models'][original_report['selected_model_by_training_cv']]['window_level']['balanced_accuracy']
    result={'dataset':'EEGMAT NEMAR nm000109 v1.0.0', 'task':'rest vs arithmetic',
       'protocol':'All feature/model candidates selected using 5-fold GroupKFold over training subjects only; original fixed held-out subjects 9/36 evaluated once.',
       'train_subjects':sorted(set(groups[tr])),'test_subjects':sorted(set(groups[te])),
       'feature_sets':{k:int(v.shape[1]) for k,v in Xsets.items()},'candidates':leaderboard,
       'selected':best,'heldout':metric_set(y[te],prediction),
       'original_heldout_selected_cv_model_balanced_accuracy':existing,
       'limitations':['Test participant sample is only 9 people; no reliable population generalization claim.','Labels describe experimental condition, not numeric cognitive load.','Candidate testing may still exhibit selection bias; no test-driven iteration accepted.'],
       'elapsed_seconds':round(time.time()-start,2)}
    (output/'report.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    artifact={'model':winning,'feature_variant':best['features'],'channels':list(ELECTRODES),'window_seconds':4.,'feature_bands':BANDS,'classes':{'0':'rest','1':'mental_arithmetic'},'dataset':'EEGMAT','trained_subjects':result['train_subjects']}
    joblib.dump(artifact,output/'model.joblib')
    print('FINAL',json.dumps({'selected':best,'heldout':result['heldout'],'old':existing},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
