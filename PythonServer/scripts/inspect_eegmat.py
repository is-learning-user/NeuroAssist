#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import json
from pathlib import Path
from neuroassist.dataset import describe_dataset
p=argparse.ArgumentParser()
p.add_argument('--data',type=Path,default=Path('data/eegmat'))
a=p.parse_args()
print(json.dumps(describe_dataset(a.data),ensure_ascii=False,indent=2))
