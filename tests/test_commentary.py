import json
from types import SimpleNamespace

import openai
import pytest

from matchday.commentary import comment


def test_ai_cache_avoids_second_call(monkeypatch, tmp_path):
    calls = []

    def parse(**kwargs):
        calls.append(kwargs)
        note = kwargs["text_format"](summary="Insufficient prediction data.", missing_data=True)
        return SimpleNamespace(output_parsed=note, id="fake-response", usage=None)

    monkeypatch.setenv("OPENAI_API_KEY", "test-placeholder-not-a-real-key")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setattr(
        openai, "OpenAI", lambda **kwargs: SimpleNamespace(responses=SimpleNamespace(parse=parse))
    )
    facts = {"prediction": None, "demo": True}
    first = comment(facts, tmp_path)
    assert first == comment(facts, tmp_path)
    assert len(calls) == 1
    assert first["note"]["missing_data"] is True
    assert json.loads(next(tmp_path.glob("*.json")).read_text()) == first


def test_ai_refusal_does_not_create_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "test-placeholder-not-a-real-key")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setattr(
        openai,
        "OpenAI",
        lambda **kwargs: SimpleNamespace(
            responses=SimpleNamespace(parse=lambda **kw: SimpleNamespace(output_parsed=None))
        ),
    )
    with pytest.raises(ValueError, match="no parsed note"):
        comment({"prediction": None}, tmp_path)
    assert list(tmp_path.iterdir()) == []
