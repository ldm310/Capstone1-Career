from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import BaseModel, ValidationError

from lv_eval.llm import GeminiAdapter


class Answer(BaseModel):
    value: int


def test_gemini_validates_json_and_counts_thinking_tokens(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "offline-test-key")
    client = Mock()
    monkeypatch.setattr("google.genai.Client", client)
    client.return_value.models.generate_content.return_value = SimpleNamespace(
        text='{"value": 7}', response_id="test",
        usage_metadata=SimpleNamespace(prompt_token_count=10, candidates_token_count=5, thoughts_token_count=3),
    )
    adapter = GeminiAdapter("gemini-2.5-flash-lite")
    result, usage = adapter.generate(operation="test", prompt="input", response_model=Answer)
    assert result.value == 7
    assert (usage.input_tokens, usage.output_tokens) == (10, 8)
    assert client.call_args.kwargs["http_options"].retry_options.attempts == 1
    client.return_value.models.generate_content.return_value.text = '{"value": "bad"}'
    with pytest.raises(ValidationError):
        adapter.generate(operation="test", prompt="input", response_model=Answer)


def test_gemini_missing_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        GeminiAdapter("gemini-2.5-flash-lite")
