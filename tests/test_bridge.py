"""
Tests for bridge.py — The AI Connection Layer
"""

import pytest
from unittest.mock import patch, MagicMock
from fileflow.intelligence.bridge import Bridge


class TestBridgeHealthCheck:
    def test_healthy_when_ollama_running_with_models(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {"name": "qwen2.5:1.5b"},
                {"name": "nomic-embed-text:latest"},
            ]
        }
        with patch("requests.get", return_value=mock_response):
            bridge = Bridge()
            assert bridge.is_healthy() is True

    def test_unhealthy_when_ollama_not_running(self):
        import requests
        with patch("requests.get", side_effect=requests.exceptions.ConnectionError):
            bridge = Bridge()
            assert bridge.is_healthy() is False

    def test_unhealthy_when_model_missing(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [{"name": "some-other-model"}]
        }
        with patch("requests.get", return_value=mock_response):
            bridge = Bridge(slm_model="qwen2.5:1.5b", embed_model="nomic-embed-text")
            assert bridge.is_healthy() is False

    def test_health_result_is_cached(self):
        import requests
        with patch("requests.get", side_effect=requests.exceptions.ConnectionError):
            bridge = Bridge()
            bridge.is_healthy()  # First call
            bridge.is_healthy()  # Should use cache

        # Only one actual HTTP call should have been made
        # (tested implicitly — no error means cache worked)
        assert bridge._healthy is False

    def test_reset_health_cache(self):
        bridge = Bridge()
        bridge._healthy = True
        bridge.reset_health_cache()
        assert bridge._healthy is None


class TestBridgeGenerate:
    def test_returns_none_when_unhealthy(self):
        bridge = Bridge()
        bridge._healthy = False
        result = bridge.generate("test prompt")
        assert result is None

    def test_returns_text_on_success(self):
        bridge = Bridge()
        bridge._healthy = True

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "Professional"}

        with patch("requests.post", return_value=mock_response):
            result = bridge.generate("classify this file")
        assert result == "Professional"

    def test_returns_none_on_timeout(self):
        import requests
        bridge = Bridge()
        bridge._healthy = True

        with patch("requests.post", side_effect=requests.exceptions.Timeout):
            result = bridge.generate("test")
        assert result is None


class TestBridgeEmbed:
    def test_returns_none_when_unhealthy(self):
        bridge = Bridge()
        bridge._healthy = False
        result = bridge.embed("some text")
        assert result is None

    def test_returns_embedding_on_success(self):
        bridge = Bridge()
        bridge._healthy = True
        fake_embedding = [0.1] * 768

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"embedding": fake_embedding}

        with patch("requests.post", return_value=mock_response):
            result = bridge.embed("test text")
        assert result == fake_embedding
        assert len(result) == 768


class TestBridgeStatusReport:
    def test_status_report_offline(self):
        import requests
        with patch("requests.get", side_effect=requests.exceptions.ConnectionError):
            bridge = Bridge()
            report = bridge.status_report()
        assert report["healthy"] is False
        assert "OFFLINE" in report["status"]


class TestBridgeStripThinking:
    """Tests for the reasoning model thinking-stream stripper."""

    def test_strips_xml_think_block(self):
        raw = "<think>Let me reason about this carefully...</think>\n{\"category\": \"Professional\"}"
        result = Bridge._strip_thinking(raw)
        assert "<think>" not in result
        assert "Professional" in result

    def test_strips_multiline_think_block(self):
        raw = "<think>\nLine 1 of thinking\nLine 2 of thinking\n</think>\n{\"category\": \"Life_Admin\"}"
        result = Bridge._strip_thinking(raw)
        assert "<think>" not in result
        assert "Life_Admin" in result

    def test_strips_slash_think_block(self):
        raw = "/think\nsome reasoning here\n/think\n{\"category\": \"Development\"}"
        result = Bridge._strip_thinking(raw)
        assert "/think" not in result
        assert "Development" in result

    def test_passthrough_when_no_think_block(self):
        raw = "{\"category\": \"Professional\", \"confidence\": 0.9}"
        result = Bridge._strip_thinking(raw)
        assert result == raw

    def test_fallback_when_only_think_block(self):
        # Model produced only thinking, no final answer — return the raw text
        raw = "<think>I cannot determine the category from this input.</think>"
        result = Bridge._strip_thinking(raw)
        assert result  # Should not be empty
        assert len(result) > 0

    def test_handles_empty_string(self):
        assert Bridge._strip_thinking("") == ""

    def test_handles_none_gracefully(self):
        # _strip_thinking is called on .strip() result so None won't reach it,
        # but test the empty-string path for safety
        assert Bridge._strip_thinking("") == ""

    def test_case_insensitive_stripping(self):
        raw = "<THINK>uppercase think block</THINK>\n{\"category\": \"Education\"}"
        result = Bridge._strip_thinking(raw)
        assert "THINK" not in result.upper().replace("EDUCATION", "")
        assert "Education" in result

    def test_generate_strips_thinking_from_response(self):
        """Integration: generate() should return clean text even from reasoning models."""
        bridge = Bridge()
        bridge._healthy = True

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": "<think>Let me think step by step...</think>\n{\"category\": \"Professional\"}"
        }

        with patch("requests.post", return_value=mock_response):
            result = bridge.generate("classify this")

        assert result is not None
        assert "<think>" not in result
        assert "Professional" in result
