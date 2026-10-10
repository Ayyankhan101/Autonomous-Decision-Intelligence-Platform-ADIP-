from vision.schema import (
    DamageSeverity,
    SceneType,
    UploadRequest,
    VisionFacts,
    VisionMode,
    VisionStatus,
)


def test_vision_facts_round_trip_and_forbid_extra():
    f = VisionFacts(
        image_sha256="ab" * 32, scene=SceneType.ACCIDENT, objects=["car"],
        damage_severity=DamageSeverity.HIGH, injuries_visible=True,
        confidence={"scene": 0.9}, model_id="mock-vlm", model_version="0.1.0",
        mode=VisionMode.MOCK, latency_ms=1.5,
    )
    assert f.status is VisionStatus.OK
    again = VisionFacts.model_validate(f.model_dump(mode="json"))
    assert again == f
    try:
        VisionFacts.model_validate({**f.model_dump(mode="json"), "bogus": 1})
        raise AssertionError("extra field must be rejected")
    except ValueError:
        pass


def test_vision_facts_failed_factory_keeps_required_fields():
    f = VisionFacts.failed(
        image_sha256="cd" * 32, mode=VisionMode.LIVE,
        model_id="qwen", model_version="4bit", latency_ms=0.0,
        status=VisionStatus.UNAVAILABLE, error_code="timeout",
    )
    assert f.status is VisionStatus.UNAVAILABLE
    assert f.error_code == "timeout"
    assert f.scene is SceneType.UNKNOWN
    assert f.damage_severity is DamageSeverity.UNKNOWN


def test_upload_request_bounds_and_forbid():
    UploadRequest(image_b64="aGk=")  # minimal ok
    for bad in ({"image_b64": ""}, {"image_b64": "aGk=", "x": 1}):
        try:
            UploadRequest.model_validate(bad)
            raise AssertionError(f"must reject {bad}")
        except ValueError:
            pass
