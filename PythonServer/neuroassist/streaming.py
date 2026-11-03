"""Reproduce genuine EEG recordings in recorded time and send model predictions.
The condition label is metadata for evaluation, never an input to the model.
"""
import asyncio
import json
from pathlib import Path
import joblib
import numpy as np
import websockets
from .dataset import read_eeg
from .features import spectral_features


def event_for_window(artifact, window, fs, index, source):
    if not isinstance(artifact, dict) or 'model' not in artifact:
        raise ValueError('Expected fitted EEGMAT model artifact')
    x = spectral_features(window, fs).reshape(1, -1)
    classifier = artifact['model']
    # One EEG window does not justify a parallel tree-worker pool.
    if hasattr(classifier, 'n_jobs'):
        classifier.n_jobs = 1
    prob = float(classifier.predict_proba(x)[0, list(classifier.classes_).index(1)])
    return {
        'schema': 'neuroassist.v1', 'type': 'prediction', 'source': source,
        'window_index': index, 'duration_s': float(window.shape[1] / fs),
        'p_task': prob, 'predicted_condition': 'arithmetic' if prob >= 0.5 else 'rest',
        'meaning': 'Probability of EEGMAT experimental condition; NOT a validated workload score',
    }


async def serve_playlist(recordings, model_path, host='127.0.0.1', port=8765, speed=1.0,
                         repeat=True, max_recording_seconds=60., ready_event=None):
    """Serve recordings in order. Each is a (path, experimental_condition) pair.

    Labels are sent for comparison in the interface but not used in prediction.
    On connection, send an immediate status message (no waiting for an EEG window).
    """
    if speed <= 0 or max_recording_seconds <= 0 or not recordings:
        raise ValueError('Positive speed/duration and at least one recording required')
    if not Path(model_path).is_file():
        raise FileNotFoundError(model_path)
    artifact = joblib.load(model_path)  # Local project artifact only.
    if hasattr(artifact['model'], 'n_jobs'):
        artifact['model'].n_jobs = 1
    window_seconds = float(artifact['window_seconds'])
    sources = []
    for path, condition in recordings:
        path = Path(path)
        if not path.is_file() or condition not in ('rest', 'arithmetic', 'unknown'):
            raise ValueError(f'Invalid recording/condition: {path}, {condition}')
        samples, fs, _ = read_eeg(path)
        window_length = round(window_seconds * fs)
        limit = min(samples.shape[1], round(max_recording_seconds * fs))
        if limit < window_length:
            raise ValueError(f'Recording too short: {path}')
        sources.append((path, condition, samples[:, :limit], fs, window_length))

    clients = set()
    current = {'file': '', 'condition': 'unknown', 'fs': 0.}

    async def broadcast(payload):
        if clients:
            packed = json.dumps(payload, ensure_ascii=False)
            await asyncio.gather(*(client.send(packed) for client in list(clients)), return_exceptions=True)

    async def handler(ws):
        clients.add(ws)
        await ws.send(json.dumps({'schema': 'neuroassist.v1', 'type': 'connected',
                                  'dataset': 'EEGMAT / NEMAR, genuine EEG recording',
                                  'recording': current['file'], 'experimental_condition': current['condition'],
                                  'sampling_rate_hz': current['fs'], 'is_replay': True}, ensure_ascii=False))
        try:
            async for _ in ws:
                pass
        except websockets.exceptions.ConnectionClosed:
            # Unity may be stopped forcibly; this is a normal client disconnect.
            pass
        finally:
            clients.discard(ws)

    print(f'WebSocket ws://{host}:{port}; {len(sources)} genuine EEG recording(s)', flush=True)
    async with websockets.serve(handler, host, port):
        if ready_event is not None:
            ready_event.set()
        # Allow a viewer to attach before the first short recording begins.
        for _ in range(20):
            if clients:
                break
            await asyncio.sleep(0.1)
        cycle = 0
        while True:
            for path, condition, samples, fs, length in sources:
                current.update(file=path.name, condition=condition, fs=fs)
                await broadcast({'schema': 'neuroassist.v1', 'type': 'recording',
                                 'recording': path.name, 'experimental_condition': condition,
                                 'sampling_rate_hz': fs, 'is_replay': True})
                for i, start in enumerate(range(0, samples.shape[1] - length + 1, length)):
                    window = samples[:, start:start+length]
                    event = event_for_window(artifact, window, fs, i, path.name)
                    event.update(replay_time_s=float(start/fs),
                                 experimental_condition=condition,
                                 rms_microvolts=float(np.sqrt(np.mean(window**2)) * 1e6),
                                 cycle=cycle)
                    await broadcast(event)
                    print(f'{condition:10s} {start/fs:5.0f}s p(task)={event["p_task"]:.3f}', flush=True)
                    await asyncio.sleep(window_seconds/speed)
            cycle += 1
            if not repeat:
                break
        await asyncio.sleep(0.3)


async def serve(edf, model_path, host='127.0.0.1', port=8765, speed=1., repeat=True):
    return await serve_playlist([(edf, 'unknown')], model_path, host, port, speed, repeat,
                                max_recording_seconds=3600.)
