"""
benchmark.py — Model Evaluation Harness
FileFlow Cognition V9

Data-driven model selection across 4 task types:
  1. Classification  — which model best categorises documents?
  2. Embedding       — which embedding model is fastest + most coherent?
  3. Summarisation   — which model writes the best one-sentence summaries?
  4. Vision          — which vision model best understands scanned documents?

After running, call apply_winners_to_settings() to write results to settings.yaml.
"""

import json
import logging
import math
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from .bridge import Bridge

logger = logging.getLogger(__name__)

# =============================================================================
# Test Fixtures
# =============================================================================

CLASSIFICATION_FIXTURES = [
    {
        "filename": "Z83_Application_Judges_Secretary.pdf",
        "content_preview": "APPLICATION FOR EMPLOYMENT Z83 FORM. Position: Judge's Secretary. Reference: HR/4/4/7/56. Department of Justice.",
        "folder_hint": "job_applications",
        "expected_category": "Professional",
    },
    {
        "filename": "lease_agreement_2024.pdf",
        "content_preview": "LEASE AGREEMENT entered into between Landlord and Tenant. Monthly rental R8500. Deposit R17000. 12-month lease.",
        "folder_hint": "life_admin",
        "expected_category": "Life_Admin",
    },
    {
        "filename": "study_guide_administrative_law.pdf",
        "content_preview": "CHAPTER 1: Introduction to Administrative Law. This guide covers the syllabus for the board exam. University of Pretoria.",
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
        "content_preview": "FIRST NATIONAL BANK. Account Statement. Account Number: 62XXXXXXXX. Balance: R12,450.00. January 2025.",
        "folder_hint": "finance",
        "expected_category": "Life_Admin",
    },
    {
        "filename": "cv_sandiso_mazibuko.docx",
        "content_preview": "CURRICULUM VITAE. Sandiso Mazibuko. LLB (University of Pretoria). Candidate Attorney. 3 years experience.",
        "folder_hint": "job_applications",
        "expected_category": "Professional",
    },
    {
        "filename": "cover_letter_werksmans.pdf",
        "content_preview": "Dear Hiring Manager, I write to apply for the position of Candidate Attorney at Werksmans Attorneys.",
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

SUMMARISATION_FIXTURES = [
    {
        "filename": "Z83_Application_Judges_Secretary.pdf",
        "content": "APPLICATION FOR EMPLOYMENT Z83 FORM. Position: Judge's Secretary. Reference: HR/4/4/7/56. Department of Justice and Constitutional Development. Applicant: Sandiso Mazibuko. ID: 9001015800088. Qualifications: LLB University of Pretoria 2022.",
        "expected_keywords": ["Z83", "Judge", "Secretary", "application"],
    },
    {
        "filename": "lease_agreement_2024.pdf",
        "content": "LEASE AGREEMENT entered into between Sandiso Mazibuko (Tenant) and Property Holdings (Landlord). Monthly rental R8500. Deposit R17000. Lease period: 1 January 2024 to 31 December 2024. Property: 12 Elm Street, Pretoria.",
        "expected_keywords": ["lease", "rental", "agreement"],
    },
    {
        "filename": "bank_statement_jan2025.pdf",
        "content": "FIRST NATIONAL BANK. Account Statement for January 2025. Account Number: 62XXXXXXXX. Opening Balance: R10,200.00. Closing Balance: R12,450.00. Transactions: Salary credit R25,000. Rent debit R8,500.",
        "expected_keywords": ["bank", "statement", "FNB", "balance"],
    },
]

VISION_PROMPT = (
    "This is a scanned South African government employment application form (Z83). "
    "Describe what you see in ONE specific sentence. "
    "Mention the document type, any visible position title, department name, or reference number. "
    "Do not start with 'This image shows'. Be direct."
)

# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ModelResult:
    model: str
    task: str
    accuracy: float
    avg_latency_ms: float
    consistency: float
    correct: int
    total: int
    score: float = 0.0          # Composite score (accuracy weighted, latency penalised)
    json_validity: float = 1.0  # Percentage of responses that parsed correctly as JSON (if applicable)
    failures: List[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class BenchmarkReport:
    timestamp: str
    task: str
    results: List[ModelResult]
    winner: str
    recommendation: str


# =============================================================================
# Benchmark Class
# =============================================================================

class Benchmark:
    """
    Runs candidate models against known test cases and reports winners
    across all 4 FileFlow AI task types.

    By default, auto-discovers all installed Ollama models and tests
    the appropriate ones for each task. Pass models= to override.
    """

    # Vision-capable model name patterns
    _VISION_PATTERNS = ["vl", "vision", "llava", "moondream", "gemma3"]

    # Embedding model name patterns
    _EMBED_PATTERNS = ["embed", "nomic"]

    # Models to EXCLUDE from chat tasks (they're embedding-only or vision-only)
    _CHAT_EXCLUDE_PATTERNS = ["embed", "nomic"]

    # Fallback lists if Ollama is unreachable
    _FALLBACK_CLASSIFY = ["qwen2.5:0.5b", "qwen2.5:1.5b", "gemma3:1b", "smollm2:1.7b"]
    _FALLBACK_EMBED    = ["nomic-embed-text", "qwen3-embedding:0.6b", "qwen3-embedding:4b"]
    _FALLBACK_SUMMARISE = ["qwen2.5:1.5b", "smollm2:1.7b", "gemma3:1b"]
    _FALLBACK_VISION   = ["moondream:latest", "llava-phi3:3.8b", "gemma3:4b"]

    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url
        self._installed_cache: Optional[List[str]] = None

    # ------------------------------------------------------------------
    # Model Discovery
    # ------------------------------------------------------------------

    def get_installed_models(self) -> List[str]:
        """Returns all model names currently installed in Ollama, sorted by size."""
        if self._installed_cache is not None:
            return self._installed_cache
        try:
            import requests as _req
            resp = _req.get(f"{self.base_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                # Sort by size ascending (smallest first = fastest first)
                models.sort(key=lambda m: m.get("size", 0))
                self._installed_cache = [m["name"] for m in models]
                return self._installed_cache
        except Exception as e:
            logger.debug(f"[Benchmark] Could not fetch installed models: {e}")
        return []

    def get_chat_models(self) -> List[str]:
        """All installed models suitable for text generation tasks."""
        installed = self.get_installed_models()
        return [
            m for m in installed
            if not any(p in m.lower() for p in self._CHAT_EXCLUDE_PATTERNS)
            and not any(p in m.lower() for p in self._VISION_PATTERNS)
        ]

    def get_vision_models(self) -> List[str]:
        """All installed models with vision capability."""
        installed = self.get_installed_models()
        return [
            m for m in installed
            if any(p in m.lower() for p in self._VISION_PATTERNS)
        ]

    def get_embed_models(self) -> List[str]:
        """All installed embedding models."""
        installed = self.get_installed_models()
        return [
            m for m in installed
            if any(p in m.lower() for p in self._EMBED_PATTERNS)
        ]

    def print_model_plan(self) -> None:
        """Prints which models will be tested for each task."""
        print("\n  📋 Models to test:")
        print(f"  Classification/Summarisation: {self.get_chat_models() or self._FALLBACK_CLASSIFY}")
        print(f"  Embedding:                    {self.get_embed_models() or self._FALLBACK_EMBED}")
        print(f"  Vision:                       {self.get_vision_models() or self._FALLBACK_VISION}")
        print()

    # ------------------------------------------------------------------
    # 1. Classification
    # ------------------------------------------------------------------

    def run_classification(
        self,
        models: Optional[List[str]] = None,
        runs_per_fixture: int = 2,
    ) -> BenchmarkReport:
        """Tests which model best classifies documents into the archive taxonomy."""
        candidates = models or self.get_chat_models() or self._FALLBACK_CLASSIFY
        candidates = self._filter_available(candidates)

        print(f"\n  Testing {len(candidates)} models × {len(CLASSIFICATION_FIXTURES)} fixtures × {runs_per_fixture} runs...")
        results = []
        for model in candidates:
            result = self._benchmark_classification(model, runs_per_fixture)
            result.score = self._composite_score(result.accuracy, result.avg_latency_ms, result.consistency)
            results.append(result)
            self._print_row(result)

        results.sort(key=lambda r: r.score, reverse=True)
        winner = results[0]
        return BenchmarkReport(
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            task="classification",
            results=results,
            winner=winner.model,
            recommendation=(
                f"Use '{winner.model}' for classification. "
                f"Accuracy: {winner.accuracy:.0%}, Latency: {winner.avg_latency_ms:.0f}ms, "
                f"Consistency: {winner.consistency:.0%}"
            ),
        )

    def _benchmark_classification(self, model: str, runs_per_fixture: int) -> ModelResult:
        bridge = self._make_bridge(slm=model)
        prompt_template = self._load_ruling_prompt()
        correct = 0
        total = len(CLASSIFICATION_FIXTURES)
        latencies, consistency_scores, failures = [], [], []

        for fixture in CLASSIFICATION_FIXTURES:
            answers = []
            for _ in range(runs_per_fixture):
                prompt = (
                    f"{prompt_template}\n\n---\n"
                    f"filename: {fixture['filename']}\n"
                    f"folder_hint: {fixture['folder_hint']}\n"
                    f"content_preview:\n{fixture['content_preview']}\n---\n"
                    f"Issue your ruling now (JSON only):"
                )
                start = time.monotonic()
                raw = bridge.generate(prompt, model=model)
                latencies.append((time.monotonic() - start) * 1000)
                answers.append(self._extract_category(raw))

            most_common = max(set(answers), key=answers.count)
            consistency_scores.append(answers.count(most_common) / len(answers))
            if most_common == fixture["expected_category"]:
                correct += 1
            else:
                failures.append(f"{fixture['filename']}: expected={fixture['expected_category']}, got={most_common}")

        return ModelResult(
            model=model, task="classification",
            accuracy=correct / total if total else 0.0,
            avg_latency_ms=sum(latencies) / len(latencies) if latencies else 0.0,
            consistency=sum(consistency_scores) / len(consistency_scores) if consistency_scores else 0.0,
            correct=correct, total=total, failures=failures,
        )

    # ------------------------------------------------------------------
    # 2. Embedding
    # ------------------------------------------------------------------

    def run_embedding(self, models: Optional[List[str]] = None) -> BenchmarkReport:
        """
        Tests embedding models on:
        - Speed (latency)
        - Semantic coherence (similar docs should have similar embeddings)
        """
        candidates = models or self.get_embed_models() or self._FALLBACK_EMBED
        candidates = self._filter_available(candidates)

        # Two semantically similar and one dissimilar text
        similar_a = "Z83 application form for Judge's Secretary position at Department of Justice."
        similar_b = "Employment application Z83 for the role of Secretary to the Judge, Justice Department."
        dissimilar = "FNB bank statement January 2025 account balance R12450."

        print(f"\n  Testing {len(candidates)} embedding models...")
        results = []

        for model in candidates:
            bridge = self._make_bridge(embed=model)
            bridge._healthy = None  # reset cache

            latencies = []
            coherence = 0.0
            success = True

            try:
                t = time.monotonic()
                vec_a = bridge.embed(similar_a, model=model)
                latencies.append((time.monotonic() - t) * 1000)

                t = time.monotonic()
                vec_b = bridge.embed(similar_b, model=model)
                latencies.append((time.monotonic() - t) * 1000)

                t = time.monotonic()
                vec_c = bridge.embed(dissimilar, model=model)
                latencies.append((time.monotonic() - t) * 1000)

                if vec_a and vec_b and vec_c:
                    sim_ab = self._cosine(vec_a, vec_b)   # Should be HIGH
                    sim_ac = self._cosine(vec_a, vec_c)   # Should be LOW
                    # Coherence: reward high sim_ab, penalise high sim_ac
                    coherence = max(0.0, sim_ab - sim_ac)
                else:
                    success = False

            except Exception as e:
                success = False
                logger.debug(f"[Benchmark] embed failed for {model}: {e}")

            dim = len(vec_a) if success and vec_a else 0
            avg_lat = sum(latencies) / len(latencies) if latencies else 9999
            notes = f"dim={dim}, coherence={coherence:.3f}"

            print(f"  {model:<35} dim={dim:<6} latency={avg_lat:.0f}ms  coherence={coherence:.3f}  ok={success}")

            result = ModelResult(
                model=model, task="embedding",
                accuracy=1.0 if success else 0.0,
                avg_latency_ms=avg_lat,
                consistency=coherence,
                correct=1 if success else 0, total=1,
                notes=notes,
            )
            result.score = self._composite_score(
                accuracy=1.0 if success else 0.0,
                latency_ms=avg_lat,
                consistency=coherence,
                latency_weight=0.3,
            )
            results.append(result)

        results.sort(key=lambda r: r.score, reverse=True)
        winner = results[0]
        return BenchmarkReport(
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            task="embedding",
            results=results,
            winner=winner.model,
            recommendation=(
                f"Use '{winner.model}' for embeddings. "
                f"Latency: {winner.avg_latency_ms:.0f}ms, {winner.notes}"
            ),
        )

    # ------------------------------------------------------------------
    # 3. Summarisation
    # ------------------------------------------------------------------

    def run_summarisation(
        self,
        models: Optional[List[str]] = None,
        runs_per_fixture: int = 2,
    ) -> BenchmarkReport:
        """
        Tests which model writes the best one-sentence document summaries.
        Scores based on: keyword coverage, length appropriateness, and consistency.
        """
        candidates = models or self.get_chat_models() or self._FALLBACK_SUMMARISE
        candidates = self._filter_available(candidates)

        print(f"\n  Testing {len(candidates)} models × {len(SUMMARISATION_FIXTURES)} fixtures...")
        results = []

        for model in candidates:
            result = self._benchmark_summarisation(model, runs_per_fixture)
            result.score = self._composite_score(result.accuracy, result.avg_latency_ms, result.consistency)
            results.append(result)
            self._print_row(result)

        results.sort(key=lambda r: r.score, reverse=True)
        winner = results[0]
        return BenchmarkReport(
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            task="summarisation",
            results=results,
            winner=winner.model,
            recommendation=(
                f"Use '{winner.model}' for summarisation. "
                f"Keyword coverage: {winner.accuracy:.0%}, Latency: {winner.avg_latency_ms:.0f}ms"
            ),
        )

    def _benchmark_summarisation(self, model: str, runs_per_fixture: int) -> ModelResult:
        bridge = self._make_bridge(slm=model)
        total = len(SUMMARISATION_FIXTURES)
        correct = 0
        latencies, consistency_scores, failures = [], [], []

        for fixture in SUMMARISATION_FIXTURES:
            summaries = []
            for _ in range(runs_per_fixture):
                prompt = (
                    f"Read the following document excerpt and write ONE specific sentence "
                    f"summarising what this document is. Be factual and direct. "
                    f"Do not start with 'This document'. Just state what it is.\n\n"
                    f"Document: {fixture['content'][:1500]}\n\nSummary:"
                )
                start = time.monotonic()
                raw = bridge.generate(prompt, model=model) or ""
                latencies.append((time.monotonic() - start) * 1000)
                # Take first sentence only
                summary = raw.strip().split(".")[0].strip()
                summaries.append(summary.lower())

            # Score: how many expected keywords appear in the best summary?
            best = max(summaries, key=len) if summaries else ""
            keywords = fixture["expected_keywords"]
            hits = sum(1 for kw in keywords if kw.lower() in best)
            keyword_score = hits / len(keywords) if keywords else 0.0

            if keyword_score >= 0.5:
                correct += 1
            else:
                failures.append(
                    f"{fixture['filename']}: missing keywords "
                    f"{[kw for kw in keywords if kw.lower() not in best]}"
                )

            # Consistency: are summaries semantically similar across runs?
            if len(summaries) > 1:
                # Simple proxy: do they share at least one keyword?
                shared = sum(
                    1 for kw in keywords
                    if all(kw.lower() in s for s in summaries)
                )
                consistency_scores.append(shared / len(keywords) if keywords else 1.0)
            else:
                consistency_scores.append(1.0)

        return ModelResult(
            model=model, task="summarisation",
            accuracy=correct / total if total else 0.0,
            avg_latency_ms=sum(latencies) / len(latencies) if latencies else 0.0,
            consistency=sum(consistency_scores) / len(consistency_scores) if consistency_scores else 0.0,
            correct=correct, total=total, failures=failures,
        )

    # ------------------------------------------------------------------
    # 4. Vision
    # ------------------------------------------------------------------

    def run_vision(
        self,
        models: Optional[List[str]] = None,
        test_image: Optional[Path] = None,
    ) -> BenchmarkReport:
        """
        Tests vision models on their ability to describe scanned documents.
        Uses a test image if provided, otherwise uses a synthetic prompt.
        """
        candidates = models or self.get_vision_models() or self._FALLBACK_VISION
        candidates = self._filter_available(candidates)

        print(f"\n  Testing {len(candidates)} vision models...")

        # If no test image provided, look for any image in common locations
        if test_image is None:
            test_image = self._find_test_image()

        results = []
        for model in candidates:
            result = self._benchmark_vision(model, test_image)
            result.score = self._composite_score(result.accuracy, result.avg_latency_ms, result.consistency)
            results.append(result)
            self._print_row(result)

        results.sort(key=lambda r: r.score, reverse=True)
        winner = results[0]
        return BenchmarkReport(
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            task="vision",
            results=results,
            winner=winner.model,
            recommendation=(
                f"Use '{winner.model}' for image understanding. "
                f"Quality: {winner.accuracy:.0%}, Latency: {winner.avg_latency_ms:.0f}ms"
            ),
        )

    def _preprocess_image(self, image_path: Path) -> str:
        """
        Deterministic image preprocessing from Vision Benchmark v2.0:
        1. Convert to RGB
        2. Resize to max 1024px (longest edge)
        3. Encode as JPEG (85% quality)
        4. Return base64 string
        """
        try:
            from PIL import Image
            import io
            import base64

            with Image.open(image_path) as img:
                # Step 1: Ensure RGB
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Step 2: Resize if needed
                w, h = img.size
                max_dim = 1024
                
                if w > max_dim or h > max_dim:
                    scale = max_dim / max(w, h)
                    new_w, new_h = int(w * scale), int(h * scale)
                    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                
                # Step 3: Encode to JPEG
                buffered = io.BytesIO()
                img.save(buffered, format="JPEG", quality=85, optimize=True)
                return base64.b64encode(buffered.getvalue()).decode('utf-8')
        except ImportError:
            # Fallback if PIL not installed (though it should be)
            import base64
            with open(image_path, "rb") as f:
                return base64.b64encode(f.read()).decode()

    def _benchmark_vision(self, model: str, test_image: Optional[Path]) -> ModelResult:
        bridge = self._make_bridge(slm=model)

        if test_image is None or not test_image.exists():
            # No image available — test with text-only proxy
            # ... (proxy code remains same, omitted for brevity if not changing) ...
            prompt = (
                "Imagine you are looking at a scanned South African Z83 employment application form. "
                "Describe what you would see in ONE sentence. Mention: document type, department, position."
            )
            start = time.monotonic()
            raw = bridge.generate(prompt, model=model) or ""
            latency = (time.monotonic() - start) * 1000

            keywords = ["Z83", "application", "employment", "department", "position"]
            hits = sum(1 for kw in keywords if kw.lower() in raw.lower())
            accuracy = hits / len(keywords)

            return ModelResult(
                model=model, task="vision",
                accuracy=accuracy,
                avg_latency_ms=latency,
                consistency=1.0,
                correct=int(accuracy >= 0.4), total=1,
                notes="text-only proxy (no test image provided)",
            )

        # With a real image
        try:
            # Use robust preprocessing
            image_b64 = self._preprocess_image(test_image)

            prompt = (
                "Look at this image carefully. Describe what you see in 2-3 sentences. "
                "Include: the type of document, who it's from, and what it's about."
            )

            bridge.timeout = 600  # Vision models on CPU need plenty of time (5-10 mins)

            start = time.monotonic()
            raw = bridge.generate(prompt, model=model, images=[image_b64]) or ""
            latency = (time.monotonic() - start) * 1000

            # Score: does the response mention document-related terms?
            doc_keywords = ["document", "form", "application", "text", "page", "scan", "letter",
                            "law", "attorney", "firm", "job", "position", "candidate", "employ",
                            "pretoria", "meyerspark", "llb", "degree"] # Specific keywords for proof of income.jpeg
            hits = sum(1 for kw in doc_keywords if kw.lower() in raw.lower())
            accuracy = hits / len(doc_keywords)

            return ModelResult(
                model=model, task="vision",
                accuracy=accuracy,
                avg_latency_ms=latency,
                consistency=1.0,
                correct=int(accuracy >= 0.2), total=1,
                notes=f"response: {raw[:200]}...",
            )
        except Exception as e:
            return ModelResult(
                model=model, task="vision",
                accuracy=0.0, avg_latency_ms=9999.0, consistency=0.0,
                correct=0, total=1,
                notes=f"error: {e}",
            )

    # ------------------------------------------------------------------
    # Run All
    # ------------------------------------------------------------------

    def run_all(
        self,
        test_image: Optional[Path] = None,
        runs_per_fixture: int = 2,
    ) -> Dict[str, BenchmarkReport]:
        """Runs all 4 benchmarks and returns a dict of task → report."""
        reports = {}

        self.print_header("Classification")
        reports["classification"] = self.run_classification(runs_per_fixture=runs_per_fixture)

        self.print_header("Embedding")
        reports["embedding"] = self.run_embedding()

        self.print_header("Summarisation")
        reports["summarisation"] = self.run_summarisation(runs_per_fixture=runs_per_fixture)

        self.print_header("Vision")
        reports["vision"] = self.run_vision(test_image=test_image)

        self.display_summary(reports)
        self.apply_winners_to_settings(reports)

        return reports

    # ------------------------------------------------------------------
    # Apply Winners to settings.yaml
    # ------------------------------------------------------------------

    def apply_winners_to_settings(
        self,
        reports: Dict[str, BenchmarkReport],
        settings_path: str = "settings.yaml",
    ) -> None:
        """
        Writes the winning models from benchmark results into settings.yaml.
        Only updates fields where a clear winner was found.
        """
        path = Path(settings_path)
        if not path.exists():
            print(f"[Benchmark] settings.yaml not found at {path}")
            return

        with open(path, "r", encoding="utf-8") as f:
            settings = yaml.safe_load(f)

        ai = settings.setdefault("ai", {})
        changed = []

        if "classification" in reports:
            winner = reports["classification"].winner
            if winner and winner != ai.get("slm_model"):
                ai["slm_model"] = winner
                changed.append(f"slm_model → {winner}")

        if "embedding" in reports:
            winner = reports["embedding"].winner
            if winner and winner != ai.get("embed_model"):
                ai["embed_model"] = winner
                changed.append(f"embed_model → {winner}")

        if "summarisation" in reports:
            winner = reports["summarisation"].winner
            if winner and winner != ai.get("summarise_model"):
                ai["summarise_model"] = winner
                changed.append(f"summarise_model → {winner}")

        if "vision" in reports:
            winner = reports["vision"].winner
            if winner and winner != ai.get("vision_model"):
                ai["vision_model"] = winner
                changed.append(f"vision_model → {winner}")

        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(settings, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        if changed:
            print(f"\n✅ settings.yaml updated:")
            for c in changed:
                print(f"   {c}")
        else:
            print("\n✅ settings.yaml already up to date.")

    # ------------------------------------------------------------------
    # Save & Load
    # ------------------------------------------------------------------

    def save_report(self, report: BenchmarkReport, output_dir: str = "reports") -> Path:
        """Saves a benchmark report to a JSON file."""
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
        return filepath

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_bridge(self, slm: str = "qwen2.5:1.5b", embed: str = "nomic-embed-text") -> Bridge:
        b = Bridge(base_url=self.base_url, slm_model=slm, embed_model=embed)
        b._healthy = True  # Skip health check during benchmarking — we call models directly
        return b

    def print_header(self, task: str):
        """Prints a bold header for a benchmark section."""
        from rich.console import Console
        from rich.panel import Panel
        console = Console()
        console.print(f"\n[bold magenta]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold magenta]")
        console.print(Panel(f"[bold white]🚀 {task.upper()} BENCHMARK[/bold white]", style="bold cyan", expand=False))
        console.print(f"[bold magenta]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold magenta]\n")

    def display_summary(self, reports: Dict[str, BenchmarkReport]):
        """Displays a beautiful final summary table of all benchmark winners."""
        from rich.console import Console
        from rich.table import Table
        from rich import box
        
        console = Console()
        table = Table(title="\n🏆 [bold underline yellow]FILEFLOW AI BENCHMARK: FINAL WINNERS[/bold underline yellow]", box=box.DOUBLE_EDGE, show_header=True, header_style="bold cyan")
        table.add_column("Task Component", style="bold white")
        table.add_column("Winning Model", style="bold green")
        table.add_column("Accuracy", justify="right")
        table.add_column("Latency (ms)", justify="right")
        table.add_column("Score", justify="right", style="bold yellow")

        for task, report in reports.items():
            # Find the winner result object to get metrics
            winner_res = next((r for r in report.results if r.model == report.winner), None)
            if not winner_res: continue
            
            table.add_row(
                task.capitalize(),
                report.winner,
                f"{winner_res.accuracy:.0%}",
                f"{winner_res.avg_latency_ms:.0f}ms",
                f"{winner_res.score:.3f}"
            )

        console.print("\n")
        console.print(table)
        console.print("\n[dim]Winners have been applied to settings.yaml. Run 'python main.py --diagnose' to verify.[/dim]\n")

    def _filter_available(self, models: List[str]) -> List[str]:
        """Removes models not installed in Ollama."""
        try:
            import requests
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if resp.status_code != 200:
                return models
            available_names = {m["name"] for m in resp.json().get("models", [])}
            # Also match without :latest suffix
            available_stems = {n.split(":")[0] for n in available_names}

            filtered = []
            for m in models:
                stem = m.split(":")[0]
                if m in available_names or f"{m}:latest" in available_names or stem in available_stems:
                    filtered.append(m)
                else:
                    logger.debug(f"[Benchmark] Skipping {m} — not installed")
            return filtered
        except Exception:
            return models  # Can't check, try all

    @staticmethod
    def _composite_score(
        accuracy: float,
        latency_ms: float,
        consistency: float,
        latency_weight: float = 0.2,
    ) -> float:
        """
        Composite score: accuracy matters most, then consistency, then speed.
        Latency is log-normalised so a 2x speed difference doesn't dominate.
        """
        latency_score = 1.0 / (1.0 + math.log1p(latency_ms / 1000.0))
        return (
            accuracy * 0.6
            + consistency * 0.2
            + latency_score * latency_weight
        )

    @staticmethod
    def _cosine(a: list, b: list) -> float:
        """Cosine similarity between two vectors."""
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        mag_a = math.sqrt(sum(x * x for x in a))
        mag_b = math.sqrt(sum(x * x for x in b))
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)

    @staticmethod
    def _print_row(result: ModelResult) -> None:
        status = "✅" if result.accuracy >= 0.7 else "⚠️ " if result.accuracy >= 0.4 else "❌"
        print(
            f"  {status} {result.model:<30} "
            f"accuracy={result.accuracy:.0%}  "
            f"latency={result.avg_latency_ms:.0f}ms  "
            f"consistency={result.consistency:.0%}  "
            f"score={result.score:.3f}"
        )

    @staticmethod
    def _find_test_image() -> Optional[Path]:
        """Looks for any image file in common locations to use as a vision test."""
        search_dirs = [
            Path.home() / "Desktop",
            Path.home() / "Downloads",
            Path.home() / "Pictures",
        ]
        extensions = [".jpg", ".jpeg", ".png"]
        for d in search_dirs:
            if d.exists():
                for ext in extensions:
                    found = list(d.glob(f"*{ext}"))
                    if found:
                        return found[0]
        return None

    def _load_ruling_prompt(self) -> str:
        prompt_path = Path(__file__).parent / "prompts" / "ruling.md"
        try:
            return prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return (
                'Classify the document. Respond with JSON only: '
                '{"category": "...", "confidence": 0.0, "reasoning": "..."}'
            )

    @staticmethod
    def _extract_category(raw: Optional[str]) -> str:
        """
        Extracts a category from a model response.
        Handles: clean JSON, markdown-fenced JSON, and prose fallback.
        """
        if not raw:
            return "Unknown"
        import re
        import json as _json

        cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`")

        # Try JSON first
        match = re.search(r"\{.*?\}", cleaned, re.DOTALL)
        if match:
            try:
                data = _json.loads(match.group())
                cat = data.get("category", "Unknown")
                if cat in ("Professional", "Education", "Development", "Life_Admin", "Waste", "Unknown"):
                    return cat
            except Exception:
                pass

        # Prose fallback: scan for category names directly
        for cat in ("Professional", "Life_Admin", "Education", "Development", "Waste"):
            if re.search(rf"\b{cat}\b", cleaned, re.IGNORECASE):
                return cat

        # Synonym scan
        synonyms = {
            "Professional": ["job application", "cv", "cover letter", "legal", "court", "attorney", "z83"],
            "Life_Admin":   ["bank statement", "lease", "invoice", "receipt", "personal finance"],
            "Education":    ["study guide", "textbook", "exam", "course", "certificate", "transcript"],
            "Development":  ["code", "script", "programming", "software", "project"],
            "Waste":        ["duplicate", "empty", "corrupted", "junk", "temporary"],
        }
        text_lower = cleaned.lower()
        for cat, keywords in synonyms.items():
            if any(kw in text_lower for kw in keywords):
                return cat

        return "Unknown"
