import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

CHUNK = 1 << 20
META_SUFFIX = ".meta.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def meta_path(path: Path) -> Path:
    return path.with_name(path.name + META_SUFFIX)


def write_meta(path: Path, url: str) -> dict[str, Any]:
    meta = {
        "url": url,
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "downloaded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    meta_path(path).write_text(json.dumps(meta, indent=2))
    return meta


def read_meta(directory: Path) -> dict[str, dict[str, Any]]:
    metas: dict[str, dict[str, Any]] = {}
    for sidecar in sorted(directory.glob("*" + META_SUFFIX)):
        metas[sidecar.name[: -len(META_SUFFIX)]] = json.loads(sidecar.read_text())
    return metas


def download_file(url: str, dest: Path, client: httpx.Client | None = None) -> Path:
    if dest.exists() and meta_path(dest).exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    owned = client is None
    http = client or httpx.Client(follow_redirects=True, timeout=httpx.Timeout(60.0, read=600.0))
    try:
        with http.stream("GET", url) as response:
            response.raise_for_status()
            with tmp.open("wb") as handle:
                for chunk in response.iter_bytes(CHUNK):
                    handle.write(chunk)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    finally:
        if owned:
            http.close()
    tmp.replace(dest)
    write_meta(dest, url)
    return dest


class DiskCache:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key: str, suffix: str) -> Path:
        return self.root / (hashlib.sha256(key.encode()).hexdigest() + suffix)

    def get(self, key: str) -> Any | None:
        target = self.path(key, ".json")
        if not target.exists():
            return None
        return json.loads(target.read_text())

    def put(self, key: str, value: Any) -> None:
        self.path(key, ".json").write_text(json.dumps(value))

    def get_text(self, key: str) -> str | None:
        target = self.path(key, ".txt")
        return target.read_text() if target.exists() else None

    def put_text(self, key: str, value: str) -> None:
        self.path(key, ".txt").write_text(value)


class RateLimiter:
    def __init__(self, min_interval: float) -> None:
        self.min_interval = min_interval
        self.last = 0.0

    def wait(self) -> None:
        delay = self.last + self.min_interval - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        self.last = time.monotonic()
