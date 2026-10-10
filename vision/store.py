"""Content-addressed image storage: bytes keyed by sha256, metadata registry
capped like jevcity's sandbox_store (oldest evicted). No wall-clock timestamps —
image metadata must never introduce a host-clock time base."""
from __future__ import annotations

import base64
import binascii
import hashlib
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from .schema import MAX_IMAGE_BYTES, VisionFacts

_EXT_BY_MIME = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
MAX_STORE_ENTRIES = 50


def sniff_mime(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def decode_b64(image_b64: str) -> bytes:
    """Strict base64 decode + size cap; raises ValueError with a client-safe message."""
    if len(image_b64) > 7_000_000:
        raise ValueError("image_b64 too large")
    try:
        data = base64.b64decode(image_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("image_b64 is not valid base64") from exc
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError(f"image exceeds {MAX_IMAGE_BYTES} bytes")
    return data


class ImageMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_id: str
    mime: str
    size_bytes: int
    facts: VisionFacts | None = None


class ImageStore:
    def __init__(self, root: Path, max_entries: int = MAX_STORE_ENTRIES) -> None:
        self.root = Path(root)
        self.max_entries = max_entries
        self._meta: dict[str, ImageMeta] = {}  # insertion order = eviction order

    def put(self, data: bytes, mime: str) -> str:
        sha = hashlib.sha256(data).hexdigest()
        ext = _EXT_BY_MIME[mime]
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{sha}.{ext}"
        if not path.exists():
            path.write_bytes(data)
        if sha not in self._meta:
            self._meta[sha] = ImageMeta(image_id=sha, mime=mime, size_bytes=len(data))
            while len(self._meta) > self.max_entries:
                old_sha = next(iter(self._meta))  # plain dict: first key = oldest
                old = self._meta.pop(old_sha)
                old_path = self.root / f"{old_sha}.{_EXT_BY_MIME[old.mime]}"
                old_path.unlink(missing_ok=True)
        return sha

    def meta(self, image_id: str) -> ImageMeta | None:
        return self._meta.get(image_id)

    def set_facts(self, image_id: str, facts: VisionFacts) -> None:
        meta = self._meta.get(image_id)
        if meta is None:
            raise KeyError(image_id)
        meta.facts = facts

    def get_bytes(self, image_id: str) -> bytes | None:
        meta = self._meta.get(image_id)
        if meta is None:
            return None
        path = self.root / f"{image_id}.{_EXT_BY_MIME[meta.mime]}"
        return path.read_bytes() if path.exists() else None

    def path(self, image_id: str) -> Path | None:
        meta = self._meta.get(image_id)
        if meta is None:
            return None
        p = self.root / f"{image_id}.{_EXT_BY_MIME[meta.mime]}"
        return p if p.exists() else None
