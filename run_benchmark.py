#!/usr/bin/env python3
"""
run_benchmark.py — FileFlow Model Benchmark Runner
FileFlow Cognition V9

Runs the model benchmark and optionally applies winners to settings.yaml.

Usage:
    python run_benchmark.py                    # All 4 tasks
    python run_benchmark.py --task classify    # Classification only
    python run_benchmark.py --task embed       # Embedding only (fastest, ~2 min)
    python run_benchmark.py --task summarise   # Summarisation only
    python run_benchmark.py --task vision      # Vision only
    python run_benchmark.py --apply            # Run all + apply winners to settings.yaml
    python run_benchmark.py --save             # Save reports to reports/
    python run_benchmark.py --image path.jpg   # Use a specific image for vision test
"""

import argparse
import sys
import time
from pathlib import Path

# Ensure the project root is on the path
sys.path.insert(0, str(Path(__file__).parent))

from fileflow.intelligence.benchmark import Benchmark


BANNER = """
╔══════════════════════════════════════════════════════════════╗
║         FileFlow Cognition V9 — Model Benchmark             ║
║         Finding the best model for each task                 ║
╚══════════════════════════════════════════════════════════════╝
"""

TASK_DESCRIPTIONS = {
    "classify":   "Which model best categorises your documents? (Z83, CV, lease, bank statement...)",
    "embed":      "Which embedding model is fastest + most semantically coherent?",
    "summarise":  "Which model writes the best one-sentence document summaries?",
    "vision":     "Which vision model best understands scanned documents and images?",
}


def main():
    parser = argparse.ArgumentParser(
        description="FileFlow Model Benchmark — find the best model for each task",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--task",
        choices=["classify", "embed", "summarise", "vision", "all"],
        default="all",
        help="Which task to benchmark (default: all)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply winners to settings.yaml after benchmarking",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save reports to reports/ directory",
    )
    parser.add_argument(
        "--image",
        type=str,
        default=None,
        help="Path to an image file to use for the vision benchmark",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=2,
        help="Number of runs per fixture for consistency testing (default: 2)",
    )
    parser.add_argument(
        "--url",
        type=str,
        default="http://localhost:11434",
        help="Ollama base URL (default: http://localhost:11434)",
    )
    args = parser.parse_args()

    print(BANNER)

    bench = Benchmark(base_url=args.url)
    test_image = Path(args.image) if args.image else None
    reports = {}
    t_total_start = time.monotonic()

    tasks_to_run = (
        ["classify", "embed", "summarise", "vision"]
        if args.task == "all"
        else [args.task]
    )

    for task in tasks_to_run:
        print(f"\n{'=' * 62}")
        print(f"  📊 {task.upper()}")
        print(f"  {TASK_DESCRIPTIONS.get(task, '')}")
        print(f"{'=' * 62}")

        t_start = time.monotonic()

        if task == "classify":
            report = bench.run_classification(runs_per_fixture=args.runs)
        elif task == "embed":
            report = bench.run_embedding()
        elif task == "summarise":
            report = bench.run_summarisation(runs_per_fixture=args.runs)
        elif task == "vision":
            report = bench.run_vision(test_image=test_image)
        else:
            continue

        elapsed = time.monotonic() - t_start
        reports[task] = report

        print(f"\n  🏆 Winner: {report.winner}")
        print(f"  💡 {report.recommendation}")
        print(f"  ⏱  Task completed in {elapsed:.1f}s")

        if args.save:
            path = bench.save_report(report)
            print(f"  📄 Saved: {path}")

    total_elapsed = time.monotonic() - t_total_start
    print(f"\n{'=' * 62}")
    print(f"  ✅ Benchmark complete in {total_elapsed:.1f}s")
    print(f"{'=' * 62}")

    # Summary table
    if len(reports) > 1:
        print("\n  📋 Summary:")
        for task, report in reports.items():
            winner_result = next((r for r in report.results if r.model == report.winner), None)
            if winner_result:
                print(
                    f"    {task:<15} → {report.winner:<30} "
                    f"(accuracy={winner_result.accuracy:.0%}, "
                    f"latency={winner_result.avg_latency_ms:.0f}ms)"
                )

    # Apply winners to settings.yaml
    if args.apply and reports:
        print(f"\n{'=' * 62}")
        print("  📝 Applying winners to settings.yaml...")
        bench.apply_winners_to_settings(reports)

    print()


if __name__ == "__main__":
    main()
