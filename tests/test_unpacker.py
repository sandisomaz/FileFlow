"""
Tests for unpacker.py — The Recursive Merge Engine

REWRITTEN: the previous version of this file tested a folder-flattening
design (FlattenProposal, SYSTEM_FOLDERS, depth-threshold rules,
report.deep_files / report.already_flat). That design doesn't exist in
the current unpacker.py. The current Unpacker groups scattered copies of
the same document by resolved *entity* (not folder depth), detects true
duplicates by content hash, and proposes a flat staging area per entity
(MergeProposal, UnpackReport.entity_groups). This file tests that design.

Uses real temp files rather than mocking extraction, since .txt files are
read straight off disk by Unpacker._extract_text() — no PDF/multiprocessing
machinery involved, so real files are simpler and more honest than mocks.
"""

import pytest
from pathlib import Path

from app.muscle.unpacker import Unpacker, MergeProposal, UnpackReport


def make_file(path: Path, content: str = "placeholder content padded to be over the ghost-file size threshold " * 10):
    """Writes a real file with enough bytes to clear Unpacker's min_file_size (512 bytes)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


class TestEntityGrouping:
    """
    With no extractor/judge configured, entity resolution falls back to
    folder-name heuristics (_entity_from_folder). Two files under a
    distinctly-named folder should be grouped under the same entity.
    """

    def test_files_in_same_named_folder_share_an_entity(self, tmp_path):
        source = tmp_path / "source"
        make_file(source / "WerksmansAttorneys" / "cv.txt")
        make_file(source / "WerksmansAttorneys" / "cover_letter.txt")

        unpacker = Unpacker(extractor=None, judge=None)
        report = unpacker.analyse(source, tmp_path / "staging")

        assert report.entity_count == 1
        entity_name = next(iter(report.entity_groups))
        assert len(report.entity_groups[entity_name]) == 2

    def test_generic_folder_names_do_not_become_entities(self, tmp_path):
        # "Downloads" is in Unpacker's generic-name skip list — a file
        # directly inside it with no stronger signal should not produce
        # an entity named "DOWNLOADS".
        source = tmp_path / "source"
        make_file(source / "Downloads" / "random_file.txt")

        unpacker = Unpacker(extractor=None, judge=None)
        report = unpacker.analyse(source, tmp_path / "staging")

        assert "DOWNLOADS" not in report.entity_groups


class TestDuplicateDetection:
    def test_identical_content_flagged_as_duplicate(self, tmp_path):
        source = tmp_path / "source"
        same_text = "Identical application content, byte for byte. " * 20
        make_file(source / "FirmA" / "application.txt", content=same_text)
        make_file(source / "FirmA" / "application_copy.txt", content=same_text)

        unpacker = Unpacker(extractor=None, judge=None)
        report = unpacker.analyse(source, tmp_path / "staging")

        assert report.duplicate_count == 1
        dup_proposals = [p for p in report.proposals if p.is_duplicate]
        assert len(dup_proposals) == 1
        assert dup_proposals[0].duplicate_of is not None

    def test_different_content_not_flagged_as_duplicate(self, tmp_path):
        source = tmp_path / "source"
        make_file(source / "FirmB" / "a.txt", content="Content one, unique. " * 20)
        make_file(source / "FirmB" / "b.txt", content="Content two, different. " * 20)

        unpacker = Unpacker(extractor=None, judge=None)
        report = unpacker.analyse(source, tmp_path / "staging")

        assert report.duplicate_count == 0


class TestIgnoredDirectories:
    def test_git_and_venv_directories_are_skipped(self, tmp_path):
        source = tmp_path / "source"
        make_file(source / ".git" / "some_config.txt")
        make_file(source / "venv" / "lib" / "installed.txt")
        make_file(source / "RealFolder" / "real_file.txt")

        unpacker = Unpacker(extractor=None, judge=None)
        report = unpacker.analyse(source, tmp_path / "staging")

        # BUGFIX: this test's own name contains "venv" as a substring
        # ("...and_venv_directories..."), and pytest's tmp_path fixture
        # builds the temp directory name from the test function name —
        # so a blind `"venv" in str(path)` check was matching pytest's
        # own auto-generated folder name, not the intentionally-created
        # venv/ subdirectory. Check path parts explicitly instead.
        result_paths = [Path(p.source) for p in report.proposals]
        assert not any(".git" in path.parts for path in result_paths)
        assert not any("venv" in path.parts for path in result_paths)
        assert any("RealFolder" in path.parts for path in result_paths)


class TestEmptyDirDetection:
    def test_finds_empty_directories(self, tmp_path):
        source = tmp_path / "source"
        make_file(source / "HasFiles" / "doc.txt")
        (source / "TrulyEmpty").mkdir(parents=True)

        unpacker = Unpacker(extractor=None, judge=None)
        report = unpacker.analyse(source, tmp_path / "staging")

        empty_names = [d.name for d in report.empty_dirs]
        assert "TrulyEmpty" in empty_names


class TestGhostFileHandling:
    def test_tiny_files_are_marked_unresolved_not_crashed_on(self, tmp_path):
        source = tmp_path / "source"
        ghost = source / "SomeFolder" / "tiny.txt"
        ghost.parent.mkdir(parents=True)
        ghost.write_text("x")  # well under the 512-byte min_file_size

        unpacker = Unpacker(extractor=None, judge=None)
        report = unpacker.analyse(source, tmp_path / "staging")

        assert ghost in report.unresolved
        assert "Too small" in report.unresolved_reasons.get(str(ghost), "")


class TestExecuteDryRun:
    def test_dry_run_does_not_write_any_files(self, tmp_path):
        source = tmp_path / "source"
        make_file(source / "FirmC" / "doc.txt")
        staging = tmp_path / "staging"

        unpacker = Unpacker(extractor=None, judge=None)
        report = unpacker.analyse(source, staging)
        result = unpacker.execute(report, dry_run=True)

        assert result.moved == len(report.proposals)
        assert not staging.exists() or not any(staging.rglob("*"))


class TestExecuteLive:
    def test_live_execute_copies_file_with_verified_integrity(self, tmp_path):
        source = tmp_path / "source"
        original_content = "Real application content for integrity check. " * 20
        make_file(source / "FirmD" / "application.txt", content=original_content)
        staging = tmp_path / "staging"

        unpacker = Unpacker(extractor=None, judge=None)
        report = unpacker.analyse(source, staging)
        result = unpacker.execute(report, dry_run=False)

        assert result.moved == 1
        assert result.failed == 0

        copied_files = list(staging.rglob("*.txt"))
        assert len(copied_files) == 1
        assert copied_files[0].read_text() == original_content

        # Original must still exist — Unpacker copies, never moves/deletes
        original = source / "FirmD" / "application.txt"
        assert original.exists()


class TestSummarise:
    def test_summary_contains_key_stats(self, tmp_path):
        source = tmp_path / "source"
        make_file(source / "FirmE" / "doc.txt")

        unpacker = Unpacker(extractor=None, judge=None)
        report = unpacker.analyse(source, tmp_path / "staging")
        summary = unpacker.summarise(report)

        # Matches the current summarise() header format, not the old
        # "Unpacker Report" / "No deep nesting" phrasing that belonged
        # to the removed flattening design.
        assert "UNPACKER ANALYSIS" in summary
        assert str(report.entity_count) in summary
        assert str(report.proposal_count) in summary

    def test_empty_source_produces_zero_proposals(self, tmp_path):
        source = tmp_path / "empty_source"
        source.mkdir()

        unpacker = Unpacker(extractor=None, judge=None)
        report = unpacker.analyse(source, tmp_path / "staging")

        assert report.proposal_count == 0
        assert report.entity_count == 0
