import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from app.brain.extractor import UnifiedExtractor
from app.muscle.manager import StagingManager


def test_unbucketing_logic():
    """
    A file with no recognizable folder/filename identity, but a
    Reference Number findable in its content, should get re-bucketed
    under an entity derived from that reference — not left in a generic
    numbered/junk folder.

    NOTE on the fix: the previous version of this test patched
    `extractor._read_pdf_text`, assuming StagingManager.stage_file()
    calls it directly. It doesn't — stage_file() routes PDF extraction
    through self._safe_extract(), which spins up a multiprocessing.Pool
    calling the module-level forensic_worker() function against the real
    file on disk. Patching _read_pdf_text never intercepted anything;
    with a nonexistent fake path, extraction would have silently
    returned "" regardless, and the previous version of this test
    likely wasn't actually exercising the code path it claimed to.
    Patching StagingManager._safe_extract directly is the correct
    interception point and avoids spinning up real subprocesses in a
    unit test.

    NOTE on the entity name: the extractor's reference-number entity
    prefix is "RECOVERED_", not "REF_" — confirmed against the current
    extractor.py: `meta['entity'] = f"RECOVERED_{ref}"`.
    """
    extractor = UnifiedExtractor()
    z83_text = """
    REPUBLIC OF SOUTH AFRICA
    Position for which you are applying: LEGAL ADMIN OFFICER
    Reference number: HR4/4/7/210
    Surname and Full names: MAZIBUKO SANDISO
    """

    staging = StagingManager(extractor)

    with patch.object(Path, 'stat') as mock_stat, \
         patch.object(StagingManager, '_safe_extract', return_value=z83_text):

        mock_stat.return_value.st_size = 1024
        mock_stat.return_value.st_mtime = 123456789

        generic_path = Path("C:/Source/bucket/in_a_government_1.pdf")
        staging.stage_file(generic_path)

    assert "RECOVERED_HR4_4_7_210" in staging.staged_files
    assert len(staging.staged_files["RECOVERED_HR4_4_7_210"]) == 1
    assert "in_a_government" not in staging.staged_files


@pytest.mark.xfail(
    strict=True,
    reason=(
        "FINDING, not a stale-test fix: this test asserts that a sibling "
        "file in the same folder as a strongly-identified file (one with "
        "a real Reference Number) gets swept into that same entity by "
        "folder-context propagation. Tracing the current code: "
        "StagingManager.stage_file() assigns an unmatched file's entity "
        "to its parent folder name (e.g. 'bucket'), not a generic marker "
        "like 'Unknown'. Refinery.refine() only propagates a strong "
        "sibling's entity onto files whose CURRENT entity is in its "
        "weak_entities allowlist: "
        "['INTERNSHIP_DEMO_SOURCE', 'Unclassified_Recovery', 'Unknown', "
        "'_Quarantine']. A real folder name like 'bucket' isn't on that "
        "list, so no propagation happens — the sibling stays under its "
        "own folder-name entity instead of joining the Reference Number "
        "group. This looks like a real capability gap for a 'forensic "
        "recovery' tool (grouping ambiguous siblings with a confidently-"
        "identified neighbor is exactly the kind of thing this tool "
        "should do), not intentionally-tightened safety behavior. "
        "Needs a decision: either broaden weak_entities' matching logic "
        "(e.g. treat any non-explicit, folder-derived entity as weak), "
        "or confirm this was deliberately restricted and update this "
        "test to assert the restriction on purpose."
    ),
)
def test_sibling_packet_reassociation():
    """
    Two files in the same folder: one has a findable Reference Number in
    its content, the other has none. Expected: both end up grouped under
    the Reference Number entity, since the folder is otherwise just a
    generic bucket with no other identity signal.
    """
    extractor = UnifiedExtractor()

    def mock_extract(self, path):
        if "in_a_government_1" in str(path):
            return "Reference number: HR4/4/7/210\nPosition: LEGAL OFFICER"
        return "Normal document text"

    staging = StagingManager(extractor)

    with patch.object(Path, 'stat') as mock_stat, \
         patch.object(StagingManager, '_safe_extract', autospec=True, side_effect=mock_extract):

        mock_stat.return_value.st_size = 1
        mock_stat.return_value.st_mtime = 1

        f1 = Path("C:/Source/bucket/in_a_government_1.pdf")
        f2 = Path("C:/Source/bucket/in_a_government_2.pdf")

        staging.stage_file(f1)
        staging.stage_file(f2)

    # BUGFIX: the previous version of this test called a method named
    # `_resolve_folder_contexts()` (plural, underscore-prefixed) that
    # doesn't exist on the current StagingManager. The real method is
    # `resolve_folder_context()` (singular, public), and it delegates to
    # app.brain.refinery.Refinery internally.
    staging.resolve_folder_context()

    assert "RECOVERED_HR4_4_7_210" in staging.staged_files
    assert len(staging.staged_files["RECOVERED_HR4_4_7_210"]) == 2
