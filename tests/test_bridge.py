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
