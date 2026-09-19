import os
import sys
from pathlib import Path

os.environ["HEREAFTER_LLM"] = "off"
os.environ["ELASTICSEARCH_URL"] = ""
os.environ["BROWSERBASE_API_KEY"] = ""
os.environ["HEREAFTER_RESEARCH"] = "off"
os.environ["HEREAFTER_DATA_KEY"] = "kq3mY0pQ3o1v2m1t0r8t5nq7n0a9uVxkq3mY0pQ3o1s="  # test-only key
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from app import config, db, state, store

    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(config, "SIM_RUNS", 200)
    db.reset(tmp_path / "test.db")
    store.reset()
    state._cache.clear()
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as c:
        c.headers["Authorization"] = "Bearer demo"
        yield c
    db.reset()
    store.reset()
