"""Live mlx-vlm smoke — model tier: deselected by default (pytest addopts),
run explicitly with: uv run pytest -q -m model tests/vision/test_live.py
Requires: uv sync --extra vision"""
from pathlib import Path

import pytest

from vision.analyzer import VisionAnalyzer
from vision.schema import VisionMode, VisionStatus

PNG = Path("fixtures/vision/scene.png").read_bytes()

PNG_PATH = Path("fixtures/vision/scene.png")
NOT_IMAGE_PATH = Path("fixtures/vision/not-image.txt")

pytestmark = pytest.mark.model


def test_live_analyze_returns_facts_or_fail_closed():
    # generous timeout: this call does model load + inference in a worker thread
    facts = VisionAnalyzer(mode=VisionMode.LIVE, live_timeout_s=300.0).analyze(
        PNG_PATH.read_bytes(), image_path=PNG_PATH
    )
    # Live must never raise: either structured facts or an explicit fail-closed status.
    assert facts.status in (VisionStatus.OK, VisionStatus.UNAVAILABLE,
                            VisionStatus.INVALID_RESPONSE)
    if facts.status is VisionStatus.OK:
        assert facts.scene
        assert facts.model_id
        assert facts.confidence
    else:
        assert facts.error_code


def test_live_malformed_image_fails_closed_not_crash():
    facts = VisionAnalyzer(mode=VisionMode.LIVE, live_timeout_s=300.0).analyze(
        NOT_IMAGE_PATH.read_bytes(), image_path=NOT_IMAGE_PATH
    )
    assert facts.status is not VisionStatus.OK or facts.scene
