"""Start a repeatable two-condition demonstration using real EDF recordings."""
import argparse
import asyncio
from pathlib import Path
from neuroassist.streaming import serve_playlist

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--rest', type=Path, default=Path('data/demo/sample_rest.edf'))
    p.add_argument('--task', type=Path, default=Path('data/demo/sample_mental_arithmetic.edf'))
    p.add_argument('--model', type=Path, default=Path('outputs/nemar_real/model.joblib'))
    p.add_argument('--port', type=int, default=8765)
    p.add_argument('--speed', type=float, default=1.)
    p.add_argument('--seconds', type=float, default=40., help='seconds per recording')
    args = p.parse_args()
    print('TRUE experimental labels are not used for model inference.', flush=True)
    print('Unity shows condition label for audit only; it adapts based on predictions.', flush=True)
    asyncio.run(serve_playlist([(args.rest, 'rest'), (args.task, 'arithmetic')], args.model,
                               port=args.port, speed=args.speed,
                               max_recording_seconds=args.seconds))

if __name__ == '__main__':
    main()
