#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import json
from pathlib import Path
from neuroassist.benchmark import run_benchmark
p=argparse.ArgumentParser()
p.add_argument('--data',type=Path,default=Path('data/eegmat'))
p.add_argument('--output',type=Path,default=Path('outputs/eegmat_benchmark'))
p.add_argument('--window-seconds',type=float,default=4)
p.add_argument('--max-seconds',type=float,default=60)
a=p.parse_args()
res=run_benchmark(a.data,a.output,a.window_seconds,a.max_seconds)
print('Source: EEGMAT EDF files; paired-subject split; REST vs MENTAL ARITHMETIC')
print('Train subjects:', ', '.join(res['train_subjects']))
print('Test subjects:', ', '.join(res['test_subjects']))
for name, scores in res['models'].items():
    print(f'{name}: balanced acc windows={scores["window_level"]["balanced_accuracy"]:.3f}; '
          f'sessions={scores["session_level"]["balanced_accuracy"]:.3f}')
print('Selected model via training-participant CV:',res['selected_model_by_training_cv'])
print('Data integrity:',res['data_integrity'])
print('Report:',a.output/'report.json')
