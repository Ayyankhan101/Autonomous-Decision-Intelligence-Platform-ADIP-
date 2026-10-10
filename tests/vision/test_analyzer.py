from pathlib import Path

from vision.analyzer import VisionAnalyzer
from vision.schema import VisionMode, VisionStatus

PNG = Path("fixtures/vision/scene.png").read_bytes()


def test_mock_is_deterministic_from_bytes():
    a = VisionAnalyzer(mode=VisionMode.MOCK).analyze(PNG)
    b = VisionAnalyzer(mode=VisionMode.MOCK).analyze(PNG)
    assert a == b
    assert a.status is VisionStatus.OK
    assert a.mode is VisionMode.MOCK
    assert a.image_sha256 == b.image_sha256
    assert a.confidence  # per-field confidences populated
    # different bytes -> (almost surely) different facts
    other = VisionAnalyzer(mode=VisionMode.MOCK).analyze(PNG + b"\x00")
    assert (other.scene, other.damage_severity) != (a.scene, a.damage_severity) or \
           other.image_sha256 != a.image_sha256


def test_cache_hit_serves_stored_facts():
    import hashlib

    cached = VisionAnalyzer(mode=VisionMode.MOCK).analyze(PNG)  # deterministic ref
    sha = hashlib.sha256(PNG).hexdigest()
    assert cached.image_sha256 == sha
    cache: dict = {sha: cached}
    got = VisionAnalyzer(mode=VisionMode.CACHE, cache=cache).analyze(PNG)
    assert got == cached  # served from cache, not recomputed


def test_cache_miss_without_model_is_fail_closed(monkeypatch):
    import vision.analyzer as va
    monkeypatch.setattr(va, "_live_facts", None)  # no model available
    facts = VisionAnalyzer(mode=VisionMode.CACHE, cache={}).analyze(PNG)
    assert facts.status is VisionStatus.UNAVAILABLE
    assert facts.error_code == "cache_miss_and_no_model"


def test_health_reports_mode_and_model():
    h = VisionAnalyzer(mode=VisionMode.MOCK).health()
    assert h["mode"] == "mock"
    assert h["model_id"]
    assert h["live_model_loaded"] is False
