import hashlib
import json
import time
from pathlib import Path

import httpx
import pytest

from ingest import common


def make_client(body: bytes, status: int = 200) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=body)

    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_download_file_writes_file_and_meta(tmp_path: Path) -> None:
    body = b"hello world"
    dest = tmp_path / "a" / "file.txt"
    path = common.download_file("https://example.org/file.txt", dest, client=make_client(body))
    assert path == dest
    assert dest.read_bytes() == body
    meta = json.loads(common.meta_path(dest).read_text())
    assert meta["url"] == "https://example.org/file.txt"
    assert meta["sha256"] == hashlib.sha256(body).hexdigest()
    assert meta["bytes"] == len(body)
    assert "downloaded_utc" in meta


def test_download_file_skips_when_present(tmp_path: Path) -> None:
    dest = tmp_path / "file.txt"
    common.download_file("https://example.org/x", dest, client=make_client(b"one"))
    common.download_file("https://example.org/x", dest, client=make_client(b"two"))
    assert dest.read_bytes() == b"one"


def test_download_file_raises_on_http_error(tmp_path: Path) -> None:
    dest = tmp_path / "file.txt"
    with pytest.raises(httpx.HTTPStatusError):
        common.download_file("https://example.org/x", dest, client=make_client(b"", 404))
    assert not dest.exists()
    assert not common.meta_path(dest).exists()


def test_read_meta_collects_sidecars(tmp_path: Path) -> None:
    common.download_file("https://example.org/a", tmp_path / "a.txt", client=make_client(b"a"))
    common.download_file("https://example.org/b", tmp_path / "b.txt", client=make_client(b"b"))
    metas = common.read_meta(tmp_path)
    assert sorted(metas) == ["a.txt", "b.txt"]
    assert metas["a.txt"]["url"] == "https://example.org/a"


def test_disk_cache_roundtrip(tmp_path: Path) -> None:
    cache = common.DiskCache(tmp_path / "c")
    assert cache.get("k") is None
    cache.put("k", {"a": 1})
    assert cache.get("k") == {"a": 1}
    assert common.DiskCache(tmp_path / "c").get("k") == {"a": 1}


def test_disk_cache_text(tmp_path: Path) -> None:
    cache = common.DiskCache(tmp_path / "c")
    cache.put_text("k", "<xml/>")
    assert cache.get_text("k") == "<xml/>"
    assert cache.get_text("missing") is None


def test_rate_limiter_spaces_calls() -> None:
    limiter = common.RateLimiter(0.05)
    start = time.monotonic()
    for _ in range(3):
        limiter.wait()
    assert time.monotonic() - start >= 0.1
