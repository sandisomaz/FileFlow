"""
Tests for unpacker.py — The Folder Flattener
"""

import pytest
from pathlib import Path

from fileflow.operations.unpacker import Unpacker, FlattenProposal, SYSTEM_FOLDERS


def build_nested_structure(root: Path):
    """Creates a realistic deeply nested folder structure for testing."""
    root.mkdir(parents=True, exist_ok=True)

    # Flat files (should NOT be proposed for flattening at depth=2)
    (root / "CV.pdf").write_bytes(b"cv content")
    (root / "Z83.pdf").write_bytes(b"z83 content")

    # One level deep (should NOT be proposed at depth=2)
    (root / "Applications").mkdir()
    (root / "Applications" / "CoverLetter.pdf").write_bytes(b"cover letter")

    # Two levels deep (AT the limit — should NOT be proposed at depth=2)
    (root / "Applications" / "Bowmans").mkdir()
    (root / "Applications" / "Bowmans" / "Brief.pdf").write_bytes(b"brief")

    # Three levels deep (OVER the limit — SHOULD be proposed)
    (root / "Applications" / "Bowmans" / "2024").mkdir()
    (root / "Applications" / "Bowmans" / "2024" / "deep_file.pdf").write_bytes(b"deep")

    # Four levels deep (SHOULD be proposed)
    (root / "Applications" / "Bowmans" / "2024" / "January").mkdir()
    (root / "Applications" / "Bowmans" / "2024" / "January" / "very_deep.pdf").write_bytes(b"very deep")

    # System folder (should be SKIPPED)
    (root / ".git").mkdir()
    (root / ".git" / "config").write_bytes(b"git config")

    return root



class TestUnpackerAnalyse:
    def test_finds_deep_files(self, tmp_path):
        source = build_nested_structure(tmp_path / "source")
        staging = tmp_path / "staging"
        unpacker = Unpacker(max_depth=2)
        report = unpacker.analyse(source, staging)
        # Should find 2 deep files (3 and 4 levels deep)
        assert report.deep_files == 2

    def test_does_not_flag_shallow_files(self, tmp_path):
        source = build_nested_structure(tmp_path / "source")
        staging = tmp_path / "staging"
        unpacker = Unpacker(max_depth=2)
        report = unpacker.analyse(source, staging)
        # Flat files + 1-level + 2-level should all be "already flat"
        assert report.already_flat >= 4  # CV, Z83, CoverLetter, Brief

    def test_skips_system_folders(self, tmp_path):
        source = build_nested_structure(tmp_path / "source")
        staging = tmp_path / "staging"
        unpacker = Unpacker(max_depth=2)
        report = unpacker.analyse(source, staging)
        # .git/config should NOT appear in proposals
        proposed_names = [p.source.name for p in report.proposals]
        assert "config" not in proposed_names

    def test_proposals_have_correct_depth(self, tmp_path):
        source = build_nested_structure(tmp_path / "source")
        staging = tmp_path / "staging"
        unpacker = Unpacker(max_depth=2)
        report = unpacker.analyse(source, staging)
        for proposal in report.proposals:
            assert proposal.depth > 2

    def test_empty_folder_returns_empty_report(self, tmp_path):
        source = tmp_path / "empty_source"
        source.mkdir()
        staging = tmp_path / "staging"
        unpacker = Unpacker(max_depth=2)
        report = unpacker.analyse(source, staging)
        assert report.deep_files == 0
        assert report.proposals == []

    def test_custom_max_depth(self, tmp_path):
        source = build_nested_structure(tmp_path / "source")
        staging = tmp_path / "staging"
        # With max_depth=1, even 2-level files should be flagged
        unpacker = Unpacker(max_depth=1)
        report = unpacker.analyse(source, staging)
        assert report.deep_files >= 3  # Brief + deep_file + very_deep


class TestUnpackerCollisionResolution:
    def test_no_collision_keeps_original_name(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        (source / "sub" / "deep").mkdir(parents=True)
        (source / "sub" / "deep" / "unique_file.pdf").write_bytes(b"content")

        staging = tmp_path / "staging"
        unpacker = Unpacker(max_depth=1)
        report = unpacker.analyse(source, staging)

        assert len(report.proposals) == 1
        assert report.proposals[0].destination.name == "unique_file.pdf"
        assert not report.proposals[0].collision_resolved

    def test_collision_adds_parent_prefix(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        # Two files with the same name in different deep folders
        (source / "FolderA" / "deep").mkdir(parents=True)
        (source / "FolderA" / "deep" / "CV.pdf").write_bytes(b"cv a")
        (source / "FolderB" / "deep").mkdir(parents=True)
        (source / "FolderB" / "deep" / "CV.pdf").write_bytes(b"cv b")

        staging = tmp_path / "staging"
        unpacker = Unpacker(max_depth=1)
        report = unpacker.analyse(source, staging)

        assert len(report.proposals) == 2
        names = {p.destination.name for p in report.proposals}
        # One should be CV.pdf, the other should have a prefix
        assert "CV.pdf" in names
        assert any(p.collision_resolved for p in report.proposals)


class TestUnpackerSummarise:
    def test_summarise_no_proposals(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        (source / "flat.pdf").write_bytes(b"content")
        staging = tmp_path / "staging"
        unpacker = Unpacker(max_depth=2)
        report = unpacker.analyse(source, staging)
        summary = unpacker.summarise(report)
        assert "No deep nesting" in summary

    def test_summarise_with_proposals(self, tmp_path):
        source = build_nested_structure(tmp_path / "source")
        staging = tmp_path / "staging"
        unpacker = Unpacker(max_depth=2)
        report = unpacker.analyse(source, staging)
        summary = unpacker.summarise(report)
        assert "Unpacker Report" in summary
        assert str(report.deep_files) in summary
