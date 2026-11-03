import argparse
import asyncio
from pathlib import Path
from neuroassist.streaming import serve

if __name__ == '__main__':
    p=argparse.ArgumentParser(description='Replay real EEGMAT EDF via WebSocket into Unity')
    p.add_argument('--edf',required=True,type=Path)
    p.add_argument('--model',default='outputs/eegmat_quick/model.joblib',type=Path)
    p.add_argument('--speed',type=float,default=1.)
    p.add_argument('--port',type=int,default=8765)
    p.add_argument('--once',action='store_true')
    a=p.parse_args()
    asyncio.run(serve(a.edf,a.model,port=a.port,speed=a.speed,repeat=not a.once))
