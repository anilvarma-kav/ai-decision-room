import json

import pytest
from fastapi.testclient import TestClient

from decision_room.app import create_app
from decision_room.demo import scenario


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("ROOM_API_TOKEN", raising=False)
    monkeypatch.setenv("ENABLE_LIVE", "0")
    return TestClient(create_app(str(tmp_path / "test.db")))


def brief(name="search"):
    d = scenario(name)
    return {"question": d["question"], "context": d["context"], "mode": "demo", "scenario": name}


def test_demo_stream_is_saved_and_exported(client):
    response = client.post("/api/decisions/stream", json=brief())
    assert response.status_code == 200
    events = [
        json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
    ]
    assert events[-1]["type"] == "done"
    report = events[-1]["report"]
    assert report["calls"] == []
    assert report["mode"] == "demo"
    assert len(report["tools"]) == 2
    identifier = report["id"]
    assert client.get(f"/api/decisions/{identifier}").json() == report
    assert client.get("/api/decisions").json()[0]["id"] == identifier
    md = client.get(f"/api/decisions/{identifier}/export").text
    assert "Curated demo fixture" in md
    assert "Unresolved disagreements" in md
    assert client.get(f"/api/decisions/{identifier}/export?format=json").json() == report
    assert not client.app.state.running


def test_edited_demo_is_rejected(client):
    data = brief()
    data["question"] = "Should I launch an unrelated business?"
    assert client.post("/api/decisions/stream", json=data).status_code == 422


def test_live_requires_explicit_enable(client):
    data = brief()
    data["mode"] = "live"
    assert client.post("/api/decisions/stream", json=data).status_code == 403


def test_optional_auth_protects_history_and_runs(client, monkeypatch):
    monkeypatch.setenv("ROOM_API_TOKEN", "test-token")
    assert client.get("/api/decisions").status_code == 401
    assert client.post("/api/decisions/stream", json=brief()).status_code == 401
    assert (
        client.get("/api/decisions", headers={"Authorization": "Bearer test-token"}).status_code
        == 200
    )


def test_cross_origin_post_is_rejected(client):
    assert (
        client.post(
            "/api/decisions/stream", json=brief(), headers={"Origin": "https://untrusted.example"}
        ).status_code
        == 403
    )


def test_concurrent_run_is_rejected(client):
    client.app.state.running = True
    assert client.post("/api/decisions/stream", json=brief()).status_code == 429


def test_unknown_id_returns_404(client):
    assert client.get("/api/decisions/missing").status_code == 404
