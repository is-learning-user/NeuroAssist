import asyncio
import json
import socket
from pathlib import Path
import websockets
from neuroassist.streaming import serve_playlist

ROOT = Path(__file__).resolve().parents[1]


def test_real_edf_websocket_roundtrip():
    async def go():
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            port = s.getsockname()[1]
        ready = asyncio.Event()
        task = asyncio.create_task(serve_playlist(
            [(ROOT/'data/demo/sample_rest.edf', 'rest'),
             (ROOT/'data/demo/sample_mental_arithmetic.edf', 'arithmetic')],
            ROOT/'outputs/nemar_real/model.joblib', port=port, speed=100,
            max_recording_seconds=4, repeat=False, ready_event=ready))
        try:
            await asyncio.wait_for(ready.wait(), timeout=20)
            async with websockets.connect(f'ws://127.0.0.1:{port}') as ws:
                seen = [json.loads(await asyncio.wait_for(ws.recv(),timeout=4)) for _ in range(3)]
                assert seen[0]['type']=='connected'
                assert any(m['type']=='prediction' for m in seen)
                pred = next(m for m in seen if m['type']=='prediction')
                assert pred['experimental_condition'] == 'rest'
                assert 0 <= pred['p_task'] <= 1
                assert pred['rms_microvolts'] >= 0
        finally:
            task.cancel()
            try: await task
            except asyncio.CancelledError: pass
    asyncio.run(go())
