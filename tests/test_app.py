import json

import gradio as gr
import pytest

import decision_room.app as ui
from decision_room.demo import replay, scenario
from decision_room.storage import Store


async def fast_replay(name, emit):
    return await replay(name, emit, delay=0)


async def completed_demo(tmp_path, monkeypatch, name="search"):
    monkeypatch.setattr(ui, "replay", fast_replay)
    data = scenario(name)
    store = Store(str(tmp_path / "test.db"))
    updates = []
    async for update in ui.stream_decision(
        data["question"],
        data["context"],
        "Curated demo",
        name,
        "openai",
        "anthropic",
        "openai",
        store,
    ):
        updates.append(update)
    return updates, store


def test_builds_gradio_app(tmp_path):
    assert isinstance(ui.create_app(str(tmp_path / "app.db")), gr.Blocks)


async def test_demo_stream_is_saved_and_exported(tmp_path, monkeypatch):
    updates, store = await completed_demo(tmp_path, monkeypatch)
    final = updates[-1]
    report = final[3]
    assert "Complete" in final[0]
    assert report["mode"] == "demo"
    assert report["calls"] == []
    assert len(report["tools"]) == 2
    assert store.get(report["id"]) == report
    assert "Recommendation" in final[1]
    assert "Strategist" in final[2]
    assert final[4].endswith(".md")
    assert json.loads(open(final[5]).read()) == report


async def test_edited_demo_is_rejected(tmp_path):
    store = Store(str(tmp_path / "test.db"))
    with pytest.raises(gr.Error, match="saved brief"):
        async for _ in ui.stream_decision(
            "Should I launch an unrelated business?",
            "",
            "Curated demo",
            "search",
            "openai",
            "anthropic",
            "openai",
            store,
        ):
            pass


async def test_live_requires_explicit_enable(tmp_path, monkeypatch):
    monkeypatch.setenv("ENABLE_LIVE", "0")
    store = Store(str(tmp_path / "test.db"))
    with pytest.raises(gr.Error, match="disabled"):
        async for _ in ui.stream_decision(
            "Should we build or buy search?",
            "",
            "Live models",
            "search",
            "openai",
            "openai",
            "openai",
            store,
        ):
            pass


async def test_saved_decision_can_be_loaded(tmp_path, monkeypatch):
    updates, store = await completed_demo(tmp_path, monkeypatch, "hosting")
    report = updates[-1][3]
    loaded = ui.load_history(report["id"], store)
    assert report["id"] in loaded[0]
    assert loaded[3] == report
