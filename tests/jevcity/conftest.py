from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
from fastapi.testclient import TestClient

from jevcity.api.app import build_engine, create_app

@pytest.fixture
def engine():
    eng = build_engine()
    yield eng
    eng.audit.close()


@pytest.fixture
def client(engine):
    app = create_app(engine)
    with TestClient(app) as c:
        yield c
