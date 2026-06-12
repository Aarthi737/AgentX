"""
Tests for Groq client — JSON extraction and error handling.
"""

import pytest
from core.groq_client import _parse_json_safe


class TestParseJsonSafe:
    """Tests for the JSON extraction helper."""

    def test_plain_json_object(self):
        raw = '{"key": "value", "num": 42}'
        result = _parse_json_safe(raw)
        assert result == {"key": "value", "num": 42}

    def test_markdown_fenced_json(self):
        raw = '```json\n{"issues": []}\n```'
        result = _parse_json_safe(raw)
        assert result == {"issues": []}

    def test_markdown_fenced_no_lang(self):
        raw = '```\n{"issues": [{"title": "Bug"}]}\n```'
        result = _parse_json_safe(raw)
        assert result["issues"][0]["title"] == "Bug"

    def test_json_embedded_in_prose(self):
        raw = 'Here is the analysis:\n{"issues": [{"title": "Found"}]}\nEnd.'
        result = _parse_json_safe(raw)
        assert result.get("issues", [{}])[0].get("title") == "Found"

    def test_invalid_json_returns_error_dict(self):
        raw = "This is not JSON at all."
        result = _parse_json_safe(raw)
        assert "error" in result
        assert result["error"] == "json_parse_failed"

    def test_empty_string_returns_error(self):
        result = _parse_json_safe("")
        assert "error" in result

    def test_nested_json(self):
        raw = '{"outer": {"inner": [1, 2, 3]}}'
        result = _parse_json_safe(raw)
        assert result["outer"]["inner"] == [1, 2, 3]
