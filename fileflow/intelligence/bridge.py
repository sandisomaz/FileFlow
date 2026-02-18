"""
bridge.py — The AI Connection Layer
FileFlow Cognition V9

Bridges the FileFlow system to locally-running Ollama models.
All AI calls flow through here. If Ollama is down, the system
gracefully falls back to V8 rule-based behavior.
"""

import json
import time
import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class Bridge:
    """
    The sovereign connection to the local AI runtime (Ollama).

    Responsibilities:
    - Health checking (is Ollama running?)
    - Text generation (ask the Judge to make a ruling)
    - Text embedding (ask the Inspector to understand a document)
    - Graceful fallback if Ollama is unavailable
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        slm_model: str = "qwen2.5:1.5b",
        embed_model: str = "nomic-embed-text",
        timeout: int = 60,   # 60s: reasoning models (qwen3, cogito, deepseek-r1) need more time
    ):
        self.base_url = base_url.rstrip("/")
        self.slm_model = slm_model
        self.embed_model = embed_model
        self.timeout = timeout
        self._healthy: Optional[bool] = None  # cached health state

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def is_healthy(self) -> bool:
        """
        Checks if Ollama is reachable and the required models are available.
        Result is cached for the lifetime of this object.
        """
        if self._healthy is not None:
            return self._healthy

        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if resp.status_code != 200:
                self._healthy = False
                return False

            available = {m["name"] for m in resp.json().get("models", [])}

            # Normalise: Ollama tags may include ":latest" suffix
            def _present(model: str) -> bool:
                return model in available or f"{model}:latest" in available or any(
                    a.startswith(model.split(":")[0]) for a in available
                )

            slm_ok = _present(self.slm_model)
            embed_ok = _present(self.embed_model)

            if not slm_ok:
                logger.warning(
                    f"[Bridge] SLM model '{self.slm_model}' not found in Ollama. "
                    f"Available: {sorted(available)}"
                )
            if not embed_ok:
                logger.warning(
                    f"[Bridge] Embed model '{self.embed_model}' not found in Ollama."
                )

            self._healthy = slm_ok and embed_ok
            return self._healthy

        except requests.exceptions.ConnectionError:
            logger.warning("[Bridge] Ollama is not running. Falling back to V8 rules.")
            self._healthy = False
            return False
        except Exception as e:
            logger.warning(f"[Bridge] Health check failed: {e}")
            self._healthy = False
            return False

    def reset_health_cache(self):
        """Force a fresh health check on next call."""
        self._healthy = None

    # ------------------------------------------------------------------
    # Generation (The Judge's voice)
    # ------------------------------------------------------------------

    def generate(self, prompt: str, model: Optional[str] = None) -> Optional[str]:
        """
        Sends a prompt to the SLM and returns the response text.
        Returns None if Ollama is unavailable or the call fails.
        """
        if not self.is_healthy():
            return None

        target_model = model or self.slm_model
        payload = {
            "model": target_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,   # Low temp = consistent, deterministic rulings
                "num_predict": 256,   # Short responses — we only need a category + reason
            },
        }

        try:
            start = time.monotonic()
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.timeout,
            )
            elapsed = time.monotonic() - start

            if resp.status_code != 200:
                logger.warning(f"[Bridge] generate() HTTP {resp.status_code}")
                return None

            result = resp.json().get("response", "").strip()
            result = self._strip_thinking(result)   # Remove <think>...</think> from reasoning models
            logger.debug(f"[Bridge] generate() → {len(result)} chars in {elapsed:.2f}s")
            return result

        except requests.exceptions.Timeout:
            logger.warning(f"[Bridge] generate() timed out after {self.timeout}s")
            return None
        except Exception as e:
            logger.warning(f"[Bridge] generate() failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Embedding (The Inspector's eye)
    # ------------------------------------------------------------------

    def embed(self, text: str, model: Optional[str] = None) -> Optional[list]:
        """
        Converts text into a vector embedding.
        Returns a list of floats, or None on failure.
        """
        if not self.is_healthy():
            return None

        target_model = model or self.embed_model
        # Truncate to avoid token limits (nomic-embed-text: 8192 tokens)
        truncated = text[:8000]

        payload = {
            "model": target_model,
            "prompt": truncated,
        }

        try:
            resp = requests.post(
                f"{self.base_url}/api/embeddings",
                json=payload,
                timeout=self.timeout,
            )

            if resp.status_code != 200:
                logger.warning(f"[Bridge] embed() HTTP {resp.status_code}")
                return None

            embedding = resp.json().get("embedding")
            if not embedding:
                logger.warning("[Bridge] embed() returned empty embedding")
                return None

            return embedding

        except requests.exceptions.Timeout:
            logger.warning(f"[Bridge] embed() timed out after {self.timeout}s")
            return None
        except Exception as e:
            logger.warning(f"[Bridge] embed() failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Thinking stream stripper
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_thinking(text: str) -> str:
        """
        Removes reasoning model thinking streams before returning the response.

        Handles formats used by:
        - qwen3 chat models:   <think>...</think>
        - deepseek-r1:         <think>...</think>
        - cogito:              <think>...</think>
        - Some variants:       /think ... /think

        The thinking block is always stripped; only the final answer is returned.
        If the model outputs ONLY a thinking block with no answer, the thinking
        content itself is returned as a fallback so we don't lose the response.
        """
        import re

        if not text:
            return text

        # Pattern 1: <think>...</think> (XML-style, most common)
        cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)

        # Pattern 2: /think ... /think (slash-style, some Ollama variants)
        cleaned = re.sub(r"/think.*?/think", "", cleaned, flags=re.DOTALL | re.IGNORECASE)

        cleaned = cleaned.strip()

        # Fallback: if stripping left nothing, return original (model only thought, no answer)
        if not cleaned:
            logger.debug("[Bridge] Model produced only a thinking block — returning raw response")
            return text.strip()

        return cleaned

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def status_report(self) -> dict:
        """Returns a dict summarising the bridge state — useful for diagnostics."""
        healthy = self.is_healthy()
        return {
            "ollama_url": self.base_url,
            "slm_model": self.slm_model,
            "embed_model": self.embed_model,
            "healthy": healthy,
            "status": "ONLINE" if healthy else "OFFLINE (V8 fallback active)",
        }
