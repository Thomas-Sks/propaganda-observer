import pytest

from observer.api.publish import snapshot_key
from observer.core import llm


def test_snapshot_key_ignores_flags_and_sorts_query():
    assert snapshot_key("POST", "/api/events/x/stories/s/investigate", {"force": "true", "cached_only": "true"}) == \
        "POST /api/events/x/stories/s/investigate"
    assert snapshot_key("GET", "/v1/provenance", {"target": "a.com", "event": "e"}) == "GET /v1/provenance?event=e&target=a.com"


def test_read_only_blocks_every_paid_client():
    token = llm.READ_ONLY.set(True)
    try:
        with pytest.raises(llm.ReadOnly):
            llm.client()
        with pytest.raises(llm.ReadOnly):
            llm.openai_client()
        with pytest.raises(llm.ReadOnly):
            llm.complete(model="gpt-x", system="s", user="u")
    finally:
        llm.READ_ONLY.reset(token)


def test_api_refuses_calls_without_internal_token():
    from fastapi.testclient import TestClient

    from observer.api.main import app
    c = TestClient(app)  # sans lifespan : pas besoin de base pour ce contrôle
    assert c.get("/api/events").status_code == 401
    assert c.get("/api/events", headers={"x-internal-token": "wrong"}).status_code == 401
    assert c.get("/api/health").status_code == 200
