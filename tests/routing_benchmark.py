"""
routing_benchmark.py — Intent Routing Integrity Tests
FileFlow V10

Verifies that the send_message() routing logic behaves deterministically
across all three system states: IDLE, CONNECTED (no audit), and CHAT.

Run this any time you change api.py routing logic to make sure it still works.

Usage:
    python tests/routing_benchmark.py
"""

import sys
import os
from pathlib import Path

# Add project root to sys.path
APP_ROOT = Path(__file__).parent.parent
sys.path.append(str(APP_ROOT))

from app.api import FileFlowAPI


class MockWindow:
    """Minimal pywebview window stub for testing."""
    def evaluate_js(self, js: str):
        pass  # Swallow JS calls — we're not rendering a UI


def _colour(text: str, code: str) -> str:
    return f"\x1b[{code}m{text}\x1b[0m"


def run_routing_benchmark():
    print()
    print(_colour("🚀 [ROUTING BENCHMARK] Verifying Deterministic Intent Integrity", "1;35"))
    print(_colour("━" * 62, "35"))

    api = FileFlowAPI(MockWindow())

    # ── Scenario 1: IDLE (no folder connected) ─────────────────────────────────
    print()
    print(_colour("[SCENARIO 1: IDLE — no folder connected]", "1;36"))
    query_1 = "Can you audit my files?"
    resp_1  = api.send_message(query_1)
    print(f"  User:  {query_1}")
    print(f"  Agent: {resp_1['text']}")

    # The API says: "I'm ready to look through your matters, but I don't know
    # which folder to start with yet. Please click the 📂 button..."
    # Scenario 1 success criteria
    success_1 = (
        "📂" in resp_1["text"]
        or "connect to your archive" in resp_1["text"].lower()
        or "don't know which folder" in resp_1["text"].lower()
        or "audit for" in resp_1["text"].lower()
        or "starting the" in resp_1["text"].lower()
        or "accessing the" in resp_1["text"].lower()
    )
    label_1 = _colour("✅ NUDGE/AUTO-SCOUT SUCCESS", "32") if success_1 else _colour("❌ FAILED — expected folder-nudge or auto-start", "31")
    print(f"  RESULT: {label_1}")

    # ── Scenario 2: CONNECTED but not yet audited ─────────────────────────────
    print()
    print(_colour("[SCENARIO 2: CONNECTED (folder set, no audit yet)]", "1;36"))
    api._current_source = Path("C:/Users/sandi/Desktop/MockFolder")

    query_2 = "Is it messy in there?"
    resp_2  = api.send_message(query_2)
    print(f"  User:  {query_2}")
    print(f"  Agent: {resp_2['text']}")

    # Now proactive: should trigger audit instead of shield block
    success_2 = (
        "haven't looked" in resp_2["text"].lower()
        or "audit now" in resp_2["text"].lower()
        or "connected to" in resp_2["text"].lower()
        or "accessing the" in resp_2["text"].lower()
        or "starting the" in resp_2["text"].lower()
    )
    label_2 = (
        _colour("✅ PROACTIVE_SUCCESS (Deterministic Bypass)", "32")
        if success_2
        else _colour("❌ FAILED — expected proactive audit trigger", "31")
    )
    print(f"  RESULT: {label_2}")

    # ── Scenario 3: General chat (must NOT be blocked) ────────────────────────
    print()
    print(_colour("[SCENARIO 3: GENERAL CHAT — must route freely]", "1;36"))
    query_3 = "How are you doing?"
    resp_3  = api.send_message(query_3)
    print(f"  User:  {query_3}")
    print(f"  Agent: {resp_3['text']}")

    # Should receive any normal chat reply — not a hard block or folder nudge
    success_3 = (
        "haven't looked" not in resp_3["text"].lower()
        and "📂" not in resp_3["text"]
        and len(resp_3["text"]) > 0
    )
    label_3 = (
        _colour("✅ PASSED (Routed to AI)", "32")
        if success_3
        else _colour("❌ FAILED — chat was incorrectly blocked", "31")
    )
    print(f"  RESULT: {label_3}")

    # ── Summary ────────────────────────────────────────────────────────────────
    print()
    print(_colour("━" * 62, "35"))
    all_pass = success_1 and success_2 and success_3
    if all_pass:
        print(_colour("🎉 ALL ROUTING TESTS PASSED — Integrity Shield is ACTIVE.", "1;32"))
    else:
        print(_colour("⚠️  SOME TESTS FAILED — Check api.py send_message() routing logic.", "1;31"))
    print()


if __name__ == "__main__":
    run_routing_benchmark()