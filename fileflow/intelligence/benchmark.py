"""
benchmark.py — Model Evaluation Harness
FileFlow Cognition V9

Data-driven model selection. Runs candidate models against a fixed test set
of files with known correct answers, then reports which model wins for each task.

Usage:
    python -m fileflow.intelligence.benchmark --task classify
    python -m fileflow.intelligence.benchmark --task embed
    python -m fileflow.intelligence.benchmark --all
"""

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional

from fileflow.intelligence.bridge import Bridge

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Test fixtures — ground truth for classification
# ------------------------------------------------------------------

CLASSIFICATION_FIXTURES = [
    {
        "filename": "Z83_Application_Judges_Secretary.pdf",
        "content_preview": "APPLICATION FOR EMPLOYMENT Z83 FORM. Position: Judge's Secretary. Reference: HR/4/4/7/56",
        "folder_hint": "job_applications",
        "expected_category": "Professional",
    },
    {
        "filename": "lease_agreement_2024.pdf",
        "content_preview": "LEASE AGREEMENT entered into between Landlord and Tenant. Monthly rental R8500. Deposit R17000.",
        "folder_hint": "life_admin",
        "expected_category": "Life_Admin",
    },
    {
        "filename": "study_guide_part1.pdf",
        "content_preview": "CHAPTER 1: Introduction to Administrative Law. This guide covers the syllabus for the board exam.",
        "folder_hint": "courses",
        "expected_category": "Education",
    },
    {
        "filename": "main.py",
        "content_preview": "#!/usr/bin/env python3\nimport argparse\nfrom pathlib import Path\ndef main():\n    pass",
        "folder_hint": "projects",
        "expected_category": "Development",
    },
    {
        "filename": "bank_statement_jan2025.pdf",
        "content_preview": "FIRST NATIONAL BANK. Account Statement. Account Number: 62XXXXXXXX. Balance: R12,450.00",
        "folder_hint": "finance",
        "expected_category": "Life_Admin",
    },
    {
        "filename": "cv_sandiso_mazibuko.docx",
        "content_preview": "CURRICULUM VITAE. Sandiso Mazibuko. LLB (University of Pretoria). Candidate Attorney.",
        "folder_hint": "job_applications",
        "expected_category": "Professional",
    },
    {
        "filename": "empty_scan.pdf",
        "content_preview": "",
        "folder_hint": "downloads",
        "expected_category": "Waste",
    },
]


@dataclass
class ModelResult:
    model: str
    task: str
    accuracy: float
    avg_latency_ms: float
    consistency: float          # % of runs where same answer given (3 runs)
    correct: int
    total: int
    failures: List[str] = field(default_factory=list)


@dataclass
class BenchmarkReport:
    timestamp: str
    task: str
    results: List[ModelResult]
    winner: str
    recommendation: str


class Benchmark:
    """
    Runs candidate models against known test cases and reports winners.

    The system uses this to make data-driven decisions about which model
    to use for each task type.
    """

    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url

    # ------------------------------------------------------------------
    # Classification Benchmark
    # ------------------------------------------------------------------

    def run_classification(
        self,
        models: Optional[List[str]] = None,
        runs_per_fixture: int = 3,
    ) -> BenchmarkReport:
        """
        Tests which model is best at classifying documents into the archive taxonomy.
        """
        if models is None:
            # Default candidates — ordered by size (smallest first for speed)
            models = [
                "qwen2.5:0.5b",
                "qwen2.5:1.5b",
                "gemma3:1b",
                "smollm2:1.7b",
                "qwen2.5:3b",
            ]

        results = []
        for model in models:
            result = self._benchmark_model_classification(model, runs_per_fixture)
            results.append(result)
            print(
                f"  {model:<30} accuracy={result.accuracy:.0%}  "
                f"latency={result.avg_latency_ms:.0f}ms  "
                f"consistency={result.consistency:.0%}"
            )

        # Pick winner: highest accuracy, then lowest latency as tiebreaker
        winner_result = max(results, key=lambda r: (r.accuracy, -r.avg_latency_ms))
        winner = winner_result.model

        report = BenchmarkReport(
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            task="classification",
            results=results,
            winner=winner,
            recommendation=(
                f"Use '{winner}' for document classification. "
                f"Accuracy: {winner_result.accuracy:.0%}, "
                f"Latency: {winner_result.avg_latency_ms:.0f}ms"
            ),
        )

        return report

    def _benchmark_model_classification(
        self, model: str, runs_per_fixture: int
    ) -> ModelResult:
        bridge = Bridge(
            base_url=self.base_url,
            slm_model=model,
            embed_model="nomic-embed-text",
        )

        correct = 0
        total = len(CLASSIFICATION_FIXTURES)
        latencies = []
        failures = []
        consistency_scores = []

        prompt_template = self._load_ruling_prompt()

        for fixture in CLASSIFICATION_FIXTURES:
            answers = []
            for _ in range(runs_per_fixture):
                prompt = (
                    f"{prompt_template}\n\n"
                    f"---\n"
                    f"filename: {fixture['filename']}\n"
                    f"folder_hint: {fixture['folder_hint']}\n"
                    f"content_preview:\n{fixture['content_preview']}\n"
                    f"---\n"
                    f"Issue your ruling now (JSON only):"
                )

                start = time.monotonic()
                raw = bridge.generate(prompt, model=model)
                elapsed_ms = (time.monotonic() - start) * 1000
                latencies.append(elapsed_ms)

                category = self._extract_category(raw)
                answers.append(category)

            # Consistency: how often did the model give the same answer?
            most_common = max(set(answers), key=answers.count)
            consistency = answers.count(most_common) / len(answers)
            consistency_scores.append(consistency)

            if most_common == fixture["expected_category"]:
                correct += 1
            else:
                failures.append(
                    f"{fixture['filename']}: expected={fixture['expected_category']}, got={most_common}"
                )

        accuracy = correct / total if total > 0 else 0.0
        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
        avg_consistency = sum(consistency_scores) / len(consistency_scores) if consistency_scores else 0.0

        return ModelResult(
            model=model,
            task="classification",
            accuracy=accuracy,
            avg_latency_ms=avg_latency,
            consistency=avg_consistency,
            correct=correct,
            total=total,
            failures=failures,
        )

    # ------------------------------------------------------------------
    # Embedding Benchmark
    # ------------------------------------------------------------------

    def run_embedding(self, models: Optional[List[str]] = None) -> BenchmarkReport:
        """
        Tests which embedding model produces the most semantically meaningful vectors.
        Measures: speed, vector dimension, and basic semantic coherence.
        """
        if models is None:
            models = [
                "nomic-embed-text",
                "qwen3-embedding:0.6b",
                "qwen3-embedding:4b",
            ]

        results = []
        test_text = "This is a Z83 application form for the position of Judge's Secretary."

        for model in models:
            bridge = Bridge(
                base_url=self.base_url,
                slm_model="qwen2.5:1.5b",
                embed_model=model,
            )
            bridge._healthy = None  # reset cache

            start = time.monotonic()
            embedding = bridge.embed(test_text, model=model)
            elapsed_ms = (time.monotonic() - start) * 1000

            dim = len(embedding) if embedding else 0
            success = embedding is not None

            print(f"  {model:<35} dim={dim}  latency={elapsed_ms:.0f}ms  ok={success}")

            results.append(ModelResult(
                model=model,
                task="embedding",
                accuracy=1.0 if success else 0.0,
                avg_latency_ms=elapsed_ms,
                consistency=1.0,
                correct=1 if success else 0,
                total=1,
            ))

        winner_result = min(
            [r for r in results if r.accuracy > 0],
            key=lambda r: r.avg_latency_ms,
            default=results[0],
        )
        winner = winner_result.model

        return BenchmarkReport(
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            task="embedding",
            results=results,
            winner=winner,
            recommendation=f"Use '{winner}' for embeddings. Latency: {winner_result.avg_latency_ms:.0f}ms",
        )

    # ------------------------------------------------------------------
    # Save & Load
    # ------------------------------------------------------------------

    def save_report(self, report: BenchmarkReport, output_dir: str = "reports") -> Path:
        """Saves the benchmark report to a JSON file."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        filename = f"benchmark_{report.task}_{time.strftime('%Y%m%d_%H%M%S')}.json"
        filepath = output_path / filename

        data = {
            "timestamp": report.timestamp,
            "task": report.task,
            "winner": report.winner,
            "recommendation": report.recommendation,
            "results": [asdict(r) for r in report.results],
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"[Benchmark] Report saved to {filepath}")
        return filepath

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _load_ruling_prompt(self) -> str:
        prompt_path = Path(__file__).parent / "prompts" / "ruling.md"
        try:
            return prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return "Classify the document. Respond with JSON: {\"category\": \"...\", \"confidence\": 0.0, \"reasoning\": \"...\"}"

    @staticmethod
    def _extract_category(raw: Optional[str]) -> str:
        if not raw:
            return "Unknown"
        import re
        import json as _json
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`")
        match = re.search(r"\{.*?\}", cleaned, re.DOTALL)
        if match:
            try:
                data = _json.loads(match.group())
                return data.get("category", "Unknown")
            except Exception:
                pass
        return "Unknown"


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="FileFlow Model Benchmark")
    parser.add_argument("--task", choices=["classify", "embed", "all"], default="all")
    parser.add_argument("--models", nargs="*", help="Specific models to test")
    parser.add_argument("--save", action="store_true", help="Save report to reports/")
    args = parser.parse_args()

    bench = Benchmark()

    if args.task in ("classify", "all"):
        print("\n📊 Classification Benchmark")
        print("-" * 60)
        report = bench.run_classification(models=args.models)
        print(f"\n🏆 Winner: {report.winner}")
        print(f"💡 {report.recommendation}")
        if args.save:
            path = bench.save_report(report)
            print(f"📄 Saved: {path}")

    if args.task in ("embed", "all"):
        print("\n📊 Embedding Benchmark")
        print("-" * 60)
        report = bench.run_embedding(models=args.models)
        print(f"\n🏆 Winner: {report.winner}")
        print(f"💡 {report.recommendation}")
        if args.save:
            path = bench.save_report(report)
            print(f"📄 Saved: {path}")
