from pathlib import Path

from vision.schema import DamageSeverity, SceneType, VisionFacts, VisionMode
from vision.store import ImageStore, sniff_mime

PNG = Path("fixtures/vision/scene.png").read_bytes()
NOT_IMAGE = Path("fixtures/vision/not-image.txt").read_bytes()


def test_sniff_mime():
    assert sniff_mime(PNG) == "image/png"
    assert sniff_mime(NOT_IMAGE) is None
    assert sniff_mime(b"\xff\xd8\xff\xe0rest") == "image/jpeg"
    assert sniff_mime(b"RIFFxxxxWEBP") == "image/webp"


def test_put_is_content_addressed_and_idempotent(tmp_path):
    store = ImageStore(tmp_path)
    sha1 = store.put(PNG, "image/png")
    sha2 = store.put(PNG, "image/png")
    assert sha1 == sha2  # same bytes -> same id
    assert store.get_bytes(sha1) == PNG
    assert (tmp_path / f"{sha1}.png").is_file()


def test_set_and_get_facts(tmp_path):
    store = ImageStore(tmp_path)
    sha = store.put(PNG, "image/png")
    assert store.meta(sha).facts is None
    facts = VisionFacts(
        image_sha256=sha, scene=SceneType.FIRE, objects=["flames"],
        damage_severity=DamageSeverity.HIGH, injuries_visible=None,
        confidence={"scene": 0.8}, model_id="mock-vlm", model_version="0.1.0",
        mode=VisionMode.MOCK, latency_ms=1.0,
    )
    store.set_facts(sha, facts)
    assert store.meta(sha).facts == facts
    assert store.meta("0" * 64) is None
    assert store.get_bytes("0" * 64) is None


def test_evicts_oldest_beyond_cap(tmp_path):
    store = ImageStore(tmp_path, max_entries=2)
    shas = [store.put(bytes([i]) * 4, "image/png") for i in range(3)]
    assert store.meta(shas[0]) is None  # oldest evicted
    assert not (tmp_path / f"{shas[0]}.png").exists()
    assert store.meta(shas[1]) is not None
    assert store.meta(shas[2]) is not None
