"""Subject-held-out benchmark; no subject appears in both train/test.

This is classification of study condition (rest vs arithmetic), NOT clinical
measurement of cognitive workload.
"""
import json
import hashlib
from collections import defaultdict
from pathlib import Path
import numpy as np
import joblib
from sklearn.model_selection import GroupShuffleSplit, GroupKFold, cross_val_score
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score, confusion_matrix
from .dataset import ELECTRODES, comparable_windows, discover
from .features import spectral_features, BANDS


def metric_set(y, p):
    return {'accuracy': float(accuracy_score(y,p)),
            'balanced_accuracy': float(balanced_accuracy_score(y,p)),
            'f1_task': float(f1_score(y,p,zero_division=0)),
            'confusion_matrix_rest_task': confusion_matrix(y,p,labels=[0,1]).tolist()}


def build_arrays(data_dir: Path, window_s: float=4., max_s:float=60.):
    X=[]; y=[]; groups=[]; offsets=[]
    for row in comparable_windows(data_dir, window_s=window_s, max_s=max_s):
        X.append(spectral_features(row['window'], row['sfreq']))
        y.append(row['label']);groups.append(row['subject']);offsets.append(row['offset_s'])
    if not X:
        raise ValueError('No windows obtained')
    return np.vstack(X),np.array(y),np.array(groups),np.array(offsets)


def provenance(data_dir: Path):
    # Check local recordings against PhysioNet checksum list, if present.
    # A missing manifest is NOT evidence that these are authentic EEGMAT.
    manifest_path = Path(data_dir) / 'SHA256SUMS.txt'
    if not manifest_path.is_file():
        description = Path(data_dir) / 'dataset_description.json'
        if description.is_file():
            return 'NEMAR nm000109 v1.0.0 BIDS release; downloaded archive supplied by user; per-file original SHA256 not independently verified'
        return 'UNVERIFIED: no official SHA256 manifest in input directory'
    checksums = {}
    for line in manifest_path.read_text(encoding='utf-8').splitlines():
        parts = line.strip().split()
        if len(parts) == 2 and len(parts[0]) == 64:
            checksums[Path(parts[1]).name] = parts[0].lower()
    for paired in discover(data_dir).values():
        for file in paired.values():
            if file.name not in checksums:
                raise ValueError(f'Missing official SHA256 expected hash: {file.name}')
            checksum = hashlib.sha256(file.read_bytes()).hexdigest()
            if checksum != checksums[file.name]:
                raise ValueError(f'SHA256 FAILED: {file.name}; recording may be corrupted')
    return 'SHA256_VERIFIED: matches local PhysioNet manifest'


def run_benchmark(data_dir: Path, output_dir: Path, window_s=4., max_s=60., test_size=.25, seed=42):
    output_dir=Path(output_dir); output_dir.mkdir(parents=True, exist_ok=True)
    data_origin=provenance(data_dir)
    X,y,groups,offsets=build_arrays(data_dir,window_s,max_s)
    if len(np.unique(groups)) < 6:
        raise ValueError('Need >= 6 paired subjects for useful held-out evaluation')
    splitter=GroupShuffleSplit(n_splits=1,test_size=test_size,random_state=seed)
    train,test=next(splitter.split(X,y,groups))
    assert not set(groups[train]).intersection(groups[test])
    constructors = {
       'dummy': lambda:DummyClassifier(strategy='most_frequent'),
       'logistic': lambda:make_pipeline(StandardScaler(), LogisticRegression(max_iter=1200,random_state=seed,class_weight='balanced')),
       'random_forest': lambda:RandomForestClassifier(n_estimators=200,min_samples_leaf=2,max_features='sqrt',random_state=seed,n_jobs=-1,class_weight='balanced')
    }
    cv=GroupKFold(n_splits=min(5,len(np.unique(groups[train]))))
    cv_balanced={}
    for name in ('logistic','random_forest'):
        cv_scores=cross_val_score(constructors[name](),X[train],y[train],groups=groups[train],
                                  cv=cv,scoring='balanced_accuracy',n_jobs=1)
        cv_balanced[name]={'mean':float(np.mean(cv_scores)), 'std':float(np.std(cv_scores)),
                           'fold_scores':cv_scores.tolist()}
    selected=max(cv_balanced, key=lambda name:cv_balanced[name]['mean'])
    results={}; models={}
    for name,make in constructors.items():
        model=make();model.fit(X[train],y[train]);models[name]=model
        pred=model.predict(X[test]);proba=model.predict_proba(X[test])[:,list(model.classes_).index(1)]
        metrics=metric_set(y[test],pred)
        # Aggregate windows per subject/condition to reduce pseudo-replication
        per_session=defaultdict(lambda:{'pred':[],'true':None})
        for ix,p in zip(test,proba):
            key=(str(groups[ix]),int(y[ix]));per_session[key]['true']=int(y[ix]);per_session[key]['pred'].append(float(p))
        session_true=np.array([val['true'] for val in per_session.values()])
        session_pred=np.array([int(np.mean(val['pred']) >= .5) for val in per_session.values()])
        results[name]={'window_level':metrics,'session_level':metric_set(session_true,session_pred)}
    best=selected
    # Winner selected solely via GroupKFold on training subjects.
    report={'data_integrity':data_origin,
            'dataset':'NEMAR EEGMAT nm000109 v1.0.0 (BIDS conversion of PhysioNet EEGMAT)','experiment':'rest vs arithmetic, NOT universal mental workload',
            'subjects':int(len(np.unique(groups))),'windows':int(len(y)),
            'window_seconds':float(window_s),'max_seconds_per_condition':float(max_s),
            'train_subjects':sorted(set(groups[train].tolist())),
            'test_subjects':sorted(set(groups[test].tolist())),
            'n_train_windows':int(len(train)),'n_test_windows':int(len(test)),
            'classes':{'0':'rest','1':'mental arithmetic'},
            'models':results,'selection_cv_training_only':cv_balanced,
            'selected_model_by_training_cv':best,
            'limits':['One subject-held-out split; scores depend on which subjects are held out.',
                     'Winner selected via CV on training participants; held-out metrics have sampling uncertainty.',
                     'No per-second cognitive-workload ground truth.',
                     'Data are offline preprocessed recordings, not a live validated interface.']}
    (output_dir/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    artifact={'model':models[best],'channels':list(ELECTRODES),'window_seconds':window_s,
              'feature_bands':BANDS,'classes':{'0':'rest','1':'mental_arithmetic'},
              'dataset':'EEGMAT','trained_subjects':report['train_subjects']}
    joblib.dump(artifact,output_dir/'model.joblib')
    return report
