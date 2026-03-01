import sys
import os
import asyncio
import json
import time
from pathlib import Path
from typing import Dict, Any, List

# Add project root to sys.path
APP_ROOT = Path(__file__).parent.parent
sys.path.append(str(APP_ROOT))

from app.brain.bridge import Bridge

# Test Dataset: The "Grandmother & 3rd Grader" Dataset
UX_TEST_CASES = [
    {
        "id": "messy_audit_01",
        "input": "hey can u look at that stuff i downloaded for the lawyer thing",
        "expected_intent": "AUDIT",
        "expected_target": "Downloads",
        "must_mention": ["matters", "looking", "legal"],
        "max_grade_level": 4 
    },
    {
        "id": "vague_search_01",
        "input": "where did i put that paper from john smith about the house",
        "expected_intent": "SEARCH",
        "expected_query": "John Smith house",
        "must_mention": ["searching", "Smith"],
        "max_grade_level": 3
    },
    {
        "id": "greeting_01",
        "input": "hello how are you doing",
        "expected_intent": "CHAT",
        "expected_target": "None",
        "must_mention": ["archives", "help"],
        "max_grade_level": 4
    }
]

class UXRouterBenchmark:
    def __init__(self):
        # Selected candidates from user's library for "The Lab"
        self.models = [
            "translategemma:latest",
            "qwen2.5:1.5b",
            "llama3.2:3b",
            "smollm2:1.7b",
            "gemma3:1b",
            "ministral-3:3b",
            "phi4-mini-reasoning:latest",
            "deepseek-r1:1.5b",
            "gemma3:4b-it-qat",
            "granite3.1-moe:latest",
            "deepscaler:latest",
            "cogito:3b"
        ] 
        self.bridge = Bridge()
        self.prompt_template = Path(APP_ROOT / "config/prompts/ux_translator_v1.md").read_text()
        
    def evaluate_simplicity(self, text: str) -> float:
        """Simple heuristic: word length and sentence complexity. Lower is better."""
        words = text.replace(".", "").replace(",", "").split()
        if not words: return 0.0
        avg_word_len = sum(len(w) for w in words) / len(words)
        # Sentence count penalty (we want ONE short sentence)
        sentence_count = text.count(".") + text.count("!") + text.count("?")
        complexity = avg_word_len + (sentence_count * 0.5)
        return round(complexity, 2)

    def _extract_json(self, raw: str) -> Dict[str, Any]:
        """Robustly extracts and parses JSON from a model's raw string output."""
        if not raw: return {}
        try:
            # 1. Try direct parse
            return json.loads(raw.strip())
        except json.JSONDecodeError:
            try:
                # 2. Extract block between { and }
                import re
                match = re.search(r"(\{.*\})", raw, re.DOTALL)
                if match:
                    return json.loads(match.group(1))
            except Exception:
                pass
        return {}

    async def run_test(self):
        print("\n\x1b[1;35m🧪 [UX ACCESSIBILITY BENCHMARK] Laboratory Mode\x1b[0m")
        print("\x1b[35m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\x1b[0m")
        
        results = {}

        for model in self.models:
            print(f"\n\x1b[1;36mTesting Model: {model}\x1b[0m")
            model_scores = {"accuracy": 0, "accessibility": 0, "brand_voice": 0, "latency": []}
            
            for case in UX_TEST_CASES:
                start_time = time.monotonic()
                prompt = self.prompt_template.replace("{user_input}", case["input"])
                
                try:
                    response_raw = self.bridge.generate(prompt, model=model) or ""
                    latency = (time.monotonic() - start_time) * 1000
                    model_scores["latency"].append(latency)
                    
                    # Attempt Robust Parse
                    data = self._extract_json(response_raw)
                    intent_match = data.get("machine_intent", "").upper() == case["expected_intent"]
                    simple_text = data.get("simple_response", "")
                    
                    # 1. Forensic Accuracy
                    if intent_match: model_scores["accuracy"] += 1
                    
                    # 2. Accessibility (Simplicity)
                    score = self.evaluate_simplicity(simple_text)
                    model_scores["accessibility"] += score
                    # 3. Brand Voice (Mandatory Tokens)
                    # We want "matters" or "archives" to appear in every simple response.
                    brand_tokens = ["matters", "archives"]
                    mentions = sum(1 for m in brand_tokens if m.lower() in simple_text.lower())
                    if mentions >= 1: model_scores["brand_voice"] += 1
                    
                    print(f"  [{case['id']}] Intent: {'✅' if intent_match else '❌'} | SimpleScore: {score} | Brand: {'✅' if mentions >= 1 else '❌'}")
                    print(f"    - Voice: \"{simple_text}\"")
                    
                except Exception as e:
                    print(f"  [{case['id']}] ERROR: {str(e)[:50]}")
            
            # Aggregate
            total = len(UX_TEST_CASES)
            results[model] = {
                "acc_pct": (model_scores["accuracy"] / total) * 100,
                "avg_simplicity": model_scores["accessibility"] / total,
                "brand_pct": (model_scores["brand_voice"] / total) * 100,
                "avg_lat": sum(model_scores["latency"]) / len(model_scores["latency"]) if model_scores["latency"] else 0
            }

        self.display_summary(results)

    def display_summary(self, results):
        print("\n\x1b[35m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\x1b[0m")
        print("\x1b[1;32m🏆 BENCHMARK RESULTS\x1b[0m")
        print(f"{'Model':<15} | {'Forensic':<10} | {'Simple':<10} | {'Brand':<8} | {'Latency':<8}")
        for model, res in results.items():
            print(f"{model:<15} | {res['acc_pct']:>8.1f}% | {res['avg_simplicity']:>10.1f} | {res['brand_pct']:>7.1f}% | {res['avg_lat']:>6.0f}ms")
        print("\x1b[35m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\x1b[0m")

if __name__ == "__main__":
    asyncio.run(UXRouterBenchmark().run_test())
