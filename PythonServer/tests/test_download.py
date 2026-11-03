import hashlib
from pathlib import Path

from scripts import download_eegmat as d


def test_sha256_manifest_parser():
    h = 'a' * 64
    assert d.manifest_from_text(f'{h} Subject00_1.edf\n') == {'Subject00_1.edf': h}
    assert d.manifest_from_text('not-checksum\n') == {}


def test_small_batch_resumes_partial_and_reuses_cache(monkeypatch, tmp_path):
    """No internet: simulate PhysioNet API and check 6 pairs + resume + cache."""
    files = {f'Subject{s:02d}_{condition}.edf': (f'DUMMY-EDF-{s}-{condition}-' * 42).encode()
             for s in range(6) for condition in (1, 2)}
    files.update({'README.txt': b'Metadata', 'subject-info.csv': b'subject,condition\n'})
    manifest = ''.join(f'{hashlib.sha256(content).hexdigest()} {name}\n'
                       for name, content in files.items()).encode()
    calls = []

    class Response:
        def __init__(self, content, status=200, headers=None):
            self.content = content
            self.status_code = status
            self.headers = headers or {}
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def raise_for_status(self):
            assert self.status_code in (200, 206)
        def iter_content(self, chunk_size=1024):
            for i in range(0, len(self.content), chunk_size):
                yield self.content[i:i + chunk_size]

    def fake_get(url, **kwargs):
        name = url.rsplit('/', 1)[-1]
        headers = kwargs.get('headers') or {}
        calls.append((name, headers.get('Range')))
        if name == 'SHA256SUMS.txt':
            return Response(manifest)
        assert name in files
        if 'Range' in headers:
            start = int(headers['Range'].removeprefix('bytes=').removesuffix('-'))
            return Response(files[name][start:], status=206,
                            headers={'Content-Range': f'bytes {start}-{len(files[name]) - 1}/{len(files[name])}'})
        return Response(files[name])

    monkeypatch.setattr(d.requests, 'get', fake_get)
    tmp_path.joinpath('Subject00_1.edf.partial').write_bytes(files['Subject00_1.edf'][:75])
    tmp_path.joinpath('Subject00_2.edf').write_bytes(files['Subject00_2.edf'])
    d.run(tmp_path, 6, workers=2)
    assert (tmp_path / 'Subject00_1.edf').read_bytes() == files['Subject00_1.edf']
    assert ('Subject00_1.edf', 'bytes=75-') in calls
    assert ('Subject00_2.edf', None) not in calls
    assert not (tmp_path / 'Subject00_1.edf.partial').exists()
    assert len(list(tmp_path.glob('Subject??_*.edf'))) == 12

    calls.clear()
    d.run(tmp_path, 6, workers=2)
    assert calls == [('SHA256SUMS.txt', None)]
