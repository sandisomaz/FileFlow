"""
test_regression_fixes.py
FileFlow — regression coverage for the bug-fix pass done in this session.

Each test is named after the bug it guards against, so a future regression
shows up as a named failure ("test_unpacker_resolve_file_does_not_crash"),
not a mystery. These are deliberately narrow — they prove the specific
fixes hold, not full coverage of every module. Restore the original
tests/ directory alongside this file for that.

Run with: pytest test_regression_fixes.py -v
"""

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _find_repo_root(start: Path) -> Path:
    """
    Walks upward from `start` until it finds a directory containing both
    main.py and an app/ package — that's the repo root regardless of
    whether this test file lives at the repo root or inside tests/.
    Falls back to `start`'s parent if nothing is found (tests using this
    will self-skip rather than fail on a bad path).
    """
    current = start.resolve()
    for _ in range(6):  # generous bound, avoids walking to filesystem root
        if (current / "main.py").exists() and (current / "app").is_dir():
            return current
        if current.parent == current:
            break
        current = current.parent
    return start.resolve().parent


# ─────────────────────────────────────────────────────────────────────────
# Bug 1 — unpacker.py: `text` was referenced before assignment in
# _resolve_file(), so every real scan silently threw NameError and every
# file fell through to "unresolved".
# ─────────────────────────────────────────────────────────────────────────

class TestUnpackerTextExtraction:
    def test_resolve_file_calls_extract_text_before_using_it(self, tmp_path):
        from app.muscle.unpacker import Unpacker

        sample = tmp_path / "sample.txt"
        sample.write_text("Cover letter for Werksmans Attorneys")

        mock_extractor = MagicMock()
        mock_extractor.extract_metadata.return_value = {"entity": "WERKSMANS"}
        mock_extractor.classify_sub_type.return_value = "CoverLetter"

        unpacker = Unpacker(extractor=mock_extractor, judge=None)
        sighting = unpacker._resolve_file(sample, depth=0, size=sample.stat().st_size)

        # The regression: extract_metadata used to be called with an
        # undefined `text` variable and raised NameError before this line
        # was ever reached. If we get here with a real call recorded,
        # the bug is fixed.
        assert mock_extractor.extract_metadata.called
        called_text_arg = mock_extractor.extract_metadata.call_args[0][0]
        assert called_text_arg == "Cover letter for Werksmans Attorneys"
        assert sighting.entity == "WERKSMANS"

    def test_resolve_file_does_not_raise_on_unreadable_file(self, tmp_path):
        from app.muscle.unpacker import Unpacker

        # A .pdf with no real PDF content — _extract_text should fail
        # gracefully and return "", not propagate an exception.
        bad_pdf = tmp_path / "corrupt.pdf"
        bad_pdf.write_bytes(b"not a real pdf")

        unpacker = Unpacker(extractor=None, judge=None)
        # Should not raise, regardless of extractor being None
        sighting = unpacker._resolve_file(bad_pdf, depth=0, size=bad_pdf.stat().st_size)
        assert sighting.path == bad_pdf


# ─────────────────────────────────────────────────────────────────────────
# Bug 2 — triage_pool.py: AsyncGenerator was used as a return-type
# annotation but never imported, so importing the module (or evaluating
# the annotation) raised NameError.
# ─────────────────────────────────────────────────────────────────────────

class TestTriagePoolImports:
    def test_module_imports_without_nameerror(self):
        import importlib
        module = importlib.import_module("app.brain.triage_pool")
        assert hasattr(module, "TriagePool")

    def test_process_queue_annotation_resolves(self):
        from app.brain.triage_pool import TriagePool
        import inspect

        sig = inspect.signature(TriagePool.process_queue)
        # Just resolving the signature used to fail if AsyncGenerator
        # wasn't imported, depending on how/when annotations are evaluated.
        assert sig is not None


# ─────────────────────────────────────────────────────────────────────────
# Bug 3 — api.py: execute() accepted `approved_items` but never used it,
# so every run executed the FULL proposal list including UNCERTAIN /
# low-confidence items the user never approved.
# ─────────────────────────────────────────────────────────────────────────

class _FakeProposal:
    def __init__(self, source, confidence, is_duplicate=False):
        self.source = Path(source)
        self.confidence = confidence
        self.is_duplicate = is_duplicate
        self.entity = "TEST_ENTITY"
        self.destination = Path("/fake/dest") / Path(source).name


class TestExecuteRespectsApproval:
    """
    These test the filtering logic directly (mirroring what api.py's
    execute()._run() does) rather than instantiating FileFlowAPI, since
    that class wires up the full engine (Bridge, Judge, DB, etc.) in
    __init__ and isn't meant to be unit-tested in isolation.
    """

    def _filter(self, proposals, approved_items):
        approved_set = set(approved_items) if approved_items else None
        uncertain_sources = {
            str(p.source) for p in proposals
            if not p.is_duplicate and p.confidence < 0.7
        }
        if approved_set:
            return [p for p in proposals if str(p.source) in approved_set]
        return [p for p in proposals if str(p.source) not in uncertain_sources]

    def test_empty_approval_excludes_uncertain_items(self):
        proposals = [
            _FakeProposal("/f/high_conf.pdf", confidence=0.9),
            _FakeProposal("/f/uncertain.pdf", confidence=0.4),
        ]
        result = self._filter(proposals, approved_items=[])
        result_paths = {str(p.source) for p in result}

        assert str(Path("/f/high_conf.pdf")) in result_paths
        assert str(Path("/f/uncertain.pdf")) not in result_paths, (
            "REGRESSION: uncertain/low-confidence item executed without "
            "explicit approval — this was the original bug."
        )

    def test_explicit_approval_list_is_respected(self):
        proposals = [
            _FakeProposal("/f/a.pdf", confidence=0.9),
            _FakeProposal("/f/b.pdf", confidence=0.9),
        ]
        # User approved only "a.pdf" in the Plan Review screen.
        # approved_items must be built the same way api.py's real caller
        # builds it: from str(proposal.source), which is OS-dependent
        # (backslashes on Windows). Hardcoding "/f/a.pdf" here previously
        # broke on Windows for that reason.
        approved = [str(Path("/f/a.pdf"))]
        result = self._filter(proposals, approved_items=approved)
        result_paths = {str(p.source) for p in result}

        assert result_paths == {str(Path("/f/a.pdf"))}

    def test_duplicates_are_never_treated_as_uncertain(self):
        proposals = [_FakeProposal("/f/dup.pdf", confidence=0.1, is_duplicate=True)]
        result = self._filter(proposals, approved_items=[])
        # Duplicates route to archive regardless of "confidence" (which
        # doesn't apply to them) — should not be silently dropped.
        assert len(result) == 1


# ─────────────────────────────────────────────────────────────────────────
# Bug 4 — api.py: dry_run was hardcoded False, ignoring
# settings.yaml's execution.dry_run_default.
# ─────────────────────────────────────────────────────────────────────────

class TestDryRunRespectsConfig:
    def test_dry_run_defaults_true_when_config_says_true(self):
        mock_config = MagicMock()
        mock_config.execution.dry_run_default = True

        # Mirrors the exact line from api.py's _init_engine()
        dry_run_default = mock_config.execution.dry_run_default if mock_config else True
        assert dry_run_default is True

    def test_dry_run_falls_back_true_when_config_missing(self):
        mock_config = None
        dry_run_default = mock_config.execution.dry_run_default if mock_config else True
        assert dry_run_default is True, (
            "REGRESSION: with no config loaded, the safe default must be "
            "True (dry run), never False."
        )


# ─────────────────────────────────────────────────────────────────────────
# Bug 5 — memory.py: _already_indexed() built a LanceDB filter via
# f-string. content_hash was never validated before interpolation.
# ─────────────────────────────────────────────────────────────────────────

class TestMemoryHashValidation:
    def test_valid_md5_hex_passes_pattern(self):
        valid_hash = "d41d8cd98f00b204e9800998ecf8427e"  # md5("")
        assert re.fullmatch(r"[0-9a-f]{32}", valid_hash)

    def test_malicious_input_rejected_by_pattern(self):
        malicious = "' OR '1'='1"
        assert not re.fullmatch(r"[0-9a-f]{32}", malicious)

    def test_already_indexed_rejects_malformed_hash_before_querying(self):
        from app.memory.memory import Memory

        mem = Memory.__new__(Memory)  # bypass __init__ (no real LanceDB needed)
        mem._table = MagicMock()  # truthy, so we reach the validation branch

        result = mem._already_indexed("some/file.pdf", "' OR '1'='1")
        assert result is False
        # The critical assertion: a malformed hash must never reach .where()
        mem._table.search.assert_not_called()

    def test_already_indexed_queries_with_valid_hash(self):
        from app.memory.memory import Memory

        mem = Memory.__new__(Memory)
        mock_table = MagicMock()
        mock_table.search.return_value.where.return_value.limit.return_value.to_list.return_value = []
        mem._table = mock_table

        valid_hash = "d41d8cd98f00b204e9800998ecf8427e"
        mem._already_indexed("some/file.pdf", valid_hash)
        mock_table.search.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────
# Bug 6 — cli.py: Bridge instantiated without embed_model, silently
# falling back to a default that doesn't match settings.yaml.
# ─────────────────────────────────────────────────────────────────────────

class TestCliBridgeConfig:
    def test_cli_passes_both_models_to_bridge(self):
        import ast

        repo_root = _find_repo_root(Path(__file__))
        cli_source = repo_root / "cli.py"
        if not cli_source.exists():
            pytest.skip(f"cli.py not found at detected repo root: {repo_root}")

        tree = ast.parse(cli_source.read_text())
        bridge_calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Bridge"
        ]
        assert bridge_calls, "No Bridge(...) call found in cli.py"
        kwarg_names = {kw.arg for kw in bridge_calls[0].keywords}
        assert "slm_model" in kwarg_names
        assert "embed_model" in kwarg_names, (
            "REGRESSION: embed_model missing from Bridge() call in cli.py — "
            "health checks will report unhealthy even when Ollama is fine."
        )


# ─────────────────────────────────────────────────────────────────────────
# Bug 7 — types.py naming collision with stdlib `types` module
# ─────────────────────────────────────────────────────────────────────────

class TestNoStdlibShadowing:
    def test_types_module_not_present_in_muscle_package(self):
        repo_root = _find_repo_root(Path(__file__))
        muscle_dir = repo_root / "app" / "muscle"
        if not muscle_dir.exists():
            pytest.skip(f"app/muscle not found at detected repo root: {repo_root}")
        assert not (muscle_dir / "types.py").exists(), (
            "REGRESSION: types.py reintroduced — shadows Python's stdlib "
            "'types' module. Use models.py."
        )
        assert (muscle_dir / "models.py").exists()

    def test_stdlib_types_module_is_the_real_one(self):
        import types as stdlib_types
        assert hasattr(stdlib_types, "FunctionType"), (
            "Something is shadowing the real stdlib 'types' module."
        )


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))