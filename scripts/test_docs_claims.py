"""Behavioral guard: a doc that asserts a shipped example *records* receipts must
have the receipt files it points to. Mechanism-description phrasing ("a live run
appends receipts to ...") describes what a run does and is not a shipped-artifact
claim, so it is not flagged."""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Assertive present-tense claim that receipts exist for a shipped example, sitting
# next to the canonical receipts glob. "records receipts" / "receipts land" are the
# shipped-artifact verbs; "a live run appends receipts to ..." is not matched.
CLAIM_RE = re.compile(
    r"(?:records?\s+receipts|receipts?\s+land)\b[^.\n]{0,40}?\.loop/receipts/\S*\.jsonl",
    re.IGNORECASE,
)
EXAMPLE_RE = re.compile(r"examples/([A-Za-z0-9_-]+)")


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _has_receipts(example_dir: Path) -> bool:
    return any((example_dir / ".loop" / "receipts").glob("*.jsonl"))


def _has_receipts_errata(changelog_text: str) -> bool:
    heading = re.search(r"^##+\s*Errata\b.*", changelog_text, re.IGNORECASE | re.MULTILINE)
    if not heading:
        return False
    section = changelog_text[heading.start():]
    nxt = re.search(r"\n##\s+\d", section)
    if nxt:
        section = section[: nxt.start()]
    return "receipt" in section.lower()


def test_no_doc_claims_shipped_receipts_that_do_not_exist():
    violations = []

    examples_root = REPO_ROOT / "examples"
    for example_dir in sorted(p for p in examples_root.glob("*") if p.is_dir()):
        for doc in sorted(example_dir.glob("*.md")):
            if CLAIM_RE.search(_collapse(doc.read_text(encoding="utf-8"))):
                if not _has_receipts(example_dir):
                    violations.append(
                        f"{doc.relative_to(REPO_ROOT)} asserts the shipped example records "
                        f"receipts, but no {example_dir.name}/.loop/receipts/*.jsonl exists"
                    )

    changelog = REPO_ROOT / "CHANGELOG.md"
    changelog_text = changelog.read_text(encoding="utf-8")
    collapsed = _collapse(changelog_text)
    for m in CLAIM_RE.finditer(collapsed):
        window = collapsed[max(0, m.start() - 120) : m.end() + 120]
        name = EXAMPLE_RE.search(window)
        if not name:
            continue
        example_dir = examples_root / name.group(1)
        if _has_receipts(example_dir):
            continue
        if _has_receipts_errata(changelog_text):
            continue
        violations.append(
            f"CHANGELOG.md asserts {name.group(1)} records receipts, but none exist "
            f"under examples/{name.group(1)}/.loop/receipts/ and no correcting Errata was found"
        )

    assert not violations, "Doc receipts claims not backed by shipped files:\n" + "\n".join(violations)
