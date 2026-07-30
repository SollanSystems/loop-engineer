"""scripts/test_docs_slice4b.py — doc parity for slice 4b.

Every assertion here was demonstrated to FAIL against the tree as it stood before the
documentation commit. A pin that passes both before and after documents nothing.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
REFERENCE = ROOT / "reference" / "repo-os-contract.md"
ADR = ROOT / "docs" / "adr" / "0002-ci-attested-verdict.md"
CODEOWNERS = ROOT / ".github" / "CODEOWNERS"
CHANGELOG = ROOT / "CHANGELOG.md"
STRUCTURAL = ROOT / "evals" / "cases" / "structural.json"

# The version at c493804, the slice's base. Tasks 1-11 land as one feature PR and every
# version surface moves only in a separate release cut.
_BASE_VERSION = "0.11.0"
_NEW_CODES = ("chain_anchor_not_ancestor", "anchor_file_unreadable", "anchor_file_invalid",
              "anchor_attestation_contradicted", "anchor_attestation_unavailable")


@pytest.fixture(scope="module")
def reference() -> str:
    return REFERENCE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def section_24(reference) -> str:
    start = reference.index("## 24.")
    return reference[start:]


@pytest.fixture(scope="module")
def amendment() -> str:
    text = ADR.read_text(encoding="utf-8")
    return text[text.index("## Amendment (2026-07-29, Slice 4b)"):]


def test_section_24_exists(reference):
    assert re.search(r"(?m)^## 24\. ", reference)


@pytest.mark.parametrize("code", _NEW_CODES)
def test_section_24_documents_every_new_issue_code(section_24, code):
    assert code in section_24


def test_section_24_documents_the_subject_file_byte_form(section_24):
    assert "64" in section_24
    assert "no trailing newline" in section_24


def test_section_23_subject_seam_paragraph_was_rewritten(reference):
    """D1 makes the retired framing false: `gh attestation verify` DOES succeed against
    the subject file's bytes now. The unqualified 'there are no bytes to fetch' claim
    must be gone."""
    seam = reference[reference.index("**The subject seam"):reference.index("## 24.")]
    assert not re.search(r"never conclude\s+.fetch the bytes, re-hash,\s*compare.", seam,
                         re.IGNORECASE)
    assert "there are no bytes to fetch" not in seam.lower()
    assert "subject-path" in seam
    assert "hashes that file's **content**" in seam


def test_section_24_records_the_rest_sunset_date(section_24):
    assert "10 Mar 2028" in section_24


def test_section_24_documents_the_public_private_asymmetry(section_24):
    assert "no transparency log" in section_24
    assert re.search(r"[Pp]rivate repositor", section_24)


def test_section_24_documents_signer_digest_as_deliberately_not_required(section_24):
    assert "signer-digest" in section_24
    assert "job_workflow_sha" in section_24
    assert "every push" in section_24


def test_section_24_carries_the_non_promoting_sentence(section_24):
    assert "non-promoting" in section_24
    assert "exactly as non-promoting as a" in section_24


def test_section_24_states_that_ancestry_is_established_by_replay(section_24):
    assert "replay" in section_24.lower()
    assert "never by trusting the\nstored `event_hash` column" in section_24 \
        or "never by trusting the stored `event_hash` column" in section_24


def test_adr_0002_carries_the_slice_4b_amendment(amendment):
    assert amendment.startswith("## Amendment (2026-07-29, Slice 4b)")


@pytest.mark.parametrize("decision", ["Decision 2", "Decision 4", "Decision 5"])
def test_amendment_names_the_three_overridden_decisions(amendment, decision):
    assert f"**{decision} —" in amendment


def test_codeowners_covers_the_anchor_path():
    text = CODEOWNERS.read_text(encoding="utf-8")
    owned = [line for line in text.splitlines()
             if line.strip() and not line.lstrip().startswith("#")
             and line.split()[0].endswith("loop-anchor.json")]
    assert owned, text
    assert owned[0].split()[1:] == ["@SollanSystems"]


def test_reference_file_count_is_still_eight():
    """§24 was APPENDED, not added as a file: structural.json pins the count at 8."""
    pinned = json.loads(STRUCTURAL.read_text(encoding="utf-8"))["reference_filenames"]
    assert len(pinned) == 8
    live = sorted(path.name for path in (ROOT / "reference").iterdir() if path.is_file())
    assert live == sorted(pinned)


def test_changelog_has_an_unreleased_slice_4b_entry():
    text = CHANGELOG.read_text(encoding="utf-8")
    unreleased = text[text.index("## Unreleased"):text.index("## 0.11.0")]
    assert "--compare" in unreleased
    assert "slice 4b" in unreleased.lower()
    assert "subject-path" in unreleased or "head-bearing file" in unreleased


def test_no_shipped_surface_still_advertises_the_retired_subject_form():
    """Fails against the tree as it stood today: the Unreleased section advertised
    `subject-digest: sha256:<chain-head>` as the shipped form and claimed 4b "does not
    ship here". Both became false the moment this slice landed."""
    unreleased_text = CHANGELOG.read_text(encoding="utf-8")
    unreleased = unreleased_text[unreleased_text.index("## Unreleased"):
                                 unreleased_text.index("## 0.11.0")]
    assert "subject-digest" not in unreleased
    assert "does not ship here" not in unreleased
    assert "subject-digest" not in (ROOT / "action.yml").read_text(encoding="utf-8")
    # 4a's code-owner sentence stays TRUE and must be KEPT: the ruleset still requires 0
    # approvals, so CODEOWNERS is not yet an operative control.
    assert "in force only once the repository ruleset requires it" in unreleased


def test_no_version_bump_in_this_slice():
    pyproject = re.search(r'(?m)^version\s*=\s*"([^"]+)"',
                          (ROOT / "pyproject.toml").read_text(encoding="utf-8")).group(1)
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert pyproject == plugin["version"] == _BASE_VERSION
