#!/usr/bin/env python3
"""PhysioNet EEGMAT downloader: partial batches, cache, resume, official SHA256.

Examples:
    python scripts/download_eegmat.py --dest data/eegmat --subjects 6 --workers 2
    python scripts/download_eegmat.py --dest data/eegmat --subjects 36 --workers 2

Files are retained between runs. Range resume is attempted when supported by
server. All complete EDFs must pass the official PhysioNet SHA256 check.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
from pathlib import Path
import re
import sys
import threading
import time
import requests

BASE = 'https://physionet.org/files/eegmat/1.0.0/'
_PRINT_LOCK = threading.Lock()


def log(message: str) -> None:
    with _PRINT_LOCK:
        print(message, flush=True)


def sha256(path: Path) -> str:
    dig = hashlib.sha256()
    with open(path, 'rb') as handle:
        for part in iter(lambda: handle.read(1 << 20), b''):
            dig.update(part)
    return dig.hexdigest()


def manifest_from_text(text: str) -> dict[str, str]:
    hashes = {}
    for line in text.splitlines():
        match = re.match(r'^([0-9a-f]{64})\s+\*?(\S+)\s*$', line.strip(), re.I)
        if match:
            hashes[Path(match.group(2)).name] = match.group(1).lower()
    return hashes


def download_bytes(url: str, timeout: int = 45) -> bytes:
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.content


def verified_cached(path: Path, expected: str) -> bool:
    return path.is_file() and sha256(path) == expected


def _download_one(name: str, target: Path, expected: str, n: int, total: int) -> None:
    """Download with best-effort byte-range resume; verify before final rename."""
    tmp = target.with_name(target.name + '.partial')
    start = tmp.stat().st_size if tmp.exists() else 0
    headers = {'Range': f'bytes={start}-'} if start else {}
    # A 416 may indicate a fully transmitted partial file left before hash checking.
    if start and sha256(tmp) == expected:
        tmp.replace(target)
        log(f'[{n}/{total}] SHA256 OK (recovered complete .partial): {name}')
        return
    try:
        with requests.get(BASE + name, headers=headers, stream=True,
                          timeout=(20, 120)) as response:
            if response.status_code == 416:
                # Partial length is wrong. Delete and let next run download again.
                tmp.unlink(missing_ok=True)
                raise RuntimeError(f'{name}: incomplete file cannot be resumed (HTTP 416). Run again.')
            response.raise_for_status()
            append = (response.status_code == 206 and start > 0)
            if append:
                content_range = response.headers.get('Content-Range', '')
                if not content_range.startswith(f'bytes {start}-'):
                    raise RuntimeError(f'{name}: unexpected Content-Range {content_range!r}')
                log(f'[{n}/{total}] resuming {name} from {start / 1048576:.1f} MiB')
            elif start:
                log(f'[{n}/{total}] server ignored Range; restarting {name}')
            else:
                log(f'[{n}/{total}] downloading {name}')
            downloaded = start if append else 0
            last_update = time.monotonic()
            with open(tmp, 'ab' if append else 'wb') as output:
                for chunk in response.iter_content(chunk_size=1 << 19):
                    if not chunk:
                        continue
                    output.write(chunk)
                    downloaded += len(chunk)
                    if time.monotonic() - last_update >= 15:
                        log(f'    {name}: received {downloaded / 1048576:.1f} MiB')
                        last_update = time.monotonic()
    except requests.RequestException:
        # On interrupted network, keep .partial for next attempt.
        log(f'    {name}: network interrupted, temporary download retained')
        raise
    digest = sha256(tmp)
    if digest != expected:
        tmp.unlink(missing_ok=True)
        raise ValueError(f'{name}: SHA256 mismatch ({digest} != {expected}); corrupt temporary file discarded')
    tmp.replace(target)
    log(f'[{n}/{total}] downloaded and SHA256 OK: {name}')


def run(dest: Path, max_subjects: int = 6, workers: int = 2) -> None:
    if not 1 <= max_subjects <= 36:
        raise ValueError('subjects must be between 1 and 36')
    if not 1 <= workers <= 3:
        raise ValueError('workers must be 1, 2 or 3')
    dest.mkdir(parents=True, exist_ok=True)
    official_manifest_text = download_bytes(BASE + 'SHA256SUMS.txt').decode('utf-8')
    manifest = manifest_from_text(official_manifest_text)
    filenames = [f'Subject{s:02d}_{condition}.edf'
                 for s in range(max_subjects) for condition in (1, 2)]
    filenames += ['README.txt', 'subject-info.csv']
    missing = [name for name in filenames if name not in manifest]
    if missing:
        raise RuntimeError(f'Official PhysioNet manifest lacks required files: {missing}')

    need_download = []
    for i, name in enumerate(filenames, 1):
        path = dest / name
        if verified_cached(path, manifest[name]):
            log(f'[{i}/{len(filenames)}] SHA256 OK (cached): {name}')
        else:
            if path.exists():
                log(f'[{i}/{len(filenames)}] outdated/broken checksum; will redownload: {name}')
                path.unlink()
            need_download.append((i, name, path, manifest[name]))

    log(f'EEGMAT: {max_subjects} subject pairs, {len(filenames)} files, '
        f'{len(need_download)} to download, {workers} concurrent downloads.')
    if need_download:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_download_one, name, path, expected, i, len(filenames)): name
                       for i, name, path, expected in need_download}
            errors = []
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as exc:
                    errors.append((futures[future], exc))
            if errors:
                for name, exc in errors:
                    log(f'DOWNLOAD ERROR {name}: {exc}')
                raise RuntimeError(f'{len(errors)} download(s) failed. Rerun; verified files will be reused.')

    # Verify selected files were all completed and authentic before claiming success.
    for name in filenames:
        if not verified_cached(dest / name, manifest[name]):
            raise RuntimeError(f'Final SHA256 validation failed: {name}')
    (dest / 'SHA256SUMS.txt').write_text(official_manifest_text, encoding='utf-8')
    (dest / 'SOURCE.txt').write_text(
        'PhysioNet EEGMAT v1.0.0\n' + BASE + '\nDOI: 10.13026/C2JQ1P\n'
        'License: Open Data Commons Attribution 1.0\n'
        f'Files SHA256-verified in this run: {len(filenames)}\n'
        f'Paired subjects requested: {max_subjects}\n', encoding='utf-8'
    )
    log(f'COMPLETE: {max_subjects} paired participants; all {len(filenames)} files verified in {dest.resolve()}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dest', type=Path, default=Path('data/eegmat'))
    parser.add_argument('--subjects', type=int, default=6,
                        help='Pairs to download, subjects 00..N-1 (6 quick, 12 preliminary, 36 full).')
    parser.add_argument('--workers', type=int, default=2,
                        help='Concurrent downloads (1..3); default 2, may not speed up a bandwidth-limited connection.')
    args = parser.parse_args()
    try:
        run(args.dest, args.subjects, args.workers)
    except (requests.RequestException, RuntimeError, ValueError) as error:
        print(f'ERROR: {error}', file=sys.stderr, flush=True)
        sys.exit(2)
