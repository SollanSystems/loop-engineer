import hashlib
import json

import pytest

from loop import contract
from loop._resources import schemas_dir
from loop.anchor import (
    ANCHOR_SCHEMA_ID,
    DEFAULT_ANCHOR_FILENAME,
    AnchorError,
    read_anchor,
)
from loop.verdict import SUBJECT_NAME, VerdictError, subject_bytes

# A real chain head this repo actually attested (run 30472017488), so the fixture is
# a value the live signer produced rather than a hand-typed 64 characters.
HEAD = "c2333cd250122cc111d5e0e97322a2458abbd1b890876d19efde750c921d6ae9"

# The five ways a 64-lowercase-hex field is malformed. Shared by the anchor reader and
# subject_bytes so the two cannot drift on what "a head" means.
MALFORMED_HEADS = [
    pytest.param(HEAD.upper(), id="uppercase"),
    pytest.param(HEAD[:63], id="63-chars"),
    pytest.param(HEAD + "a", id="65-chars"),
    pytest.param(HEAD + "\n", id="trailing-newline"),
    pytest.param("z" * 64, id="non-hex"),
]


def _anchor(**overrides):
    document = {"schema": ANCHOR_SCHEMA_ID, "chain_head": HEAD, "sequence": 41,
                "attestation_id": "37747063", "run_id": "coverage-repair",
                "recorded_at": "2026-07-29T00:00:00+00:00"}
    document.update(overrides)
    return document


def _write(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = document if isinstance(document, str) else json.dumps(document)
    path.write_text(payload, encoding="utf-8")
    return path


def _load_schema():
    return json.loads((schemas_dir() / "anchor.schema.json").read_text(encoding="utf-8"))


def _patterns_without_maxlength(node, trail=()):
    """Every subschema carrying a `pattern` but no sibling `maxLength`."""
    offenders = []
    if isinstance(node, dict):
        if "pattern" in node and "maxLength" not in node:
            offenders.append("/".join(trail) or "<root>")
        for key, value in node.items():
            offenders.extend(_patterns_without_maxlength(value, trail + (str(key),)))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            offenders.extend(_patterns_without_maxlength(value, trail + (str(index),)))
    return offenders


def test_anchor_schema_id_and_default_filename_are_pinned():
    assert ANCHOR_SCHEMA_ID == "loop-engineer/anchor@1"
    assert DEFAULT_ANCHOR_FILENAME == "loop-anchor.json"


def test_anchor_schema_file_declares_the_matching_id():
    schema = _load_schema()
    assert schema["$id"] == ANCHOR_SCHEMA_ID
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_anchor_schema_is_not_a_contract_artifact():
    # anchor@1 is a carry channel, not a contract object; SCHEMA_IDS is what doctor
    # validates a workspace against, and an anchor is not part of a workspace.
    assert ANCHOR_SCHEMA_ID not in contract.SCHEMA_IDS


def test_anchor_schema_pattern_carries_a_maxlength():
    # jsonschema's `pattern` is re.search semantics, so an anchored pattern alone
    # still accepts a trailing newline — the hole PR #89 closed for the other schemas.
    assert _patterns_without_maxlength(_load_schema()) == []


def test_anchor_schema_validates_the_shipped_example_anchor():
    jsonschema = pytest.importorskip("jsonschema")
    validator = jsonschema.Draft202012Validator(_load_schema())
    assert list(validator.iter_errors(_anchor())) == []


def test_read_anchor_returns_the_carried_head(tmp_path):
    anchor = read_anchor(_write(tmp_path / DEFAULT_ANCHOR_FILENAME, _anchor()))
    assert anchor["chain_head"] == HEAD
    assert anchor["sequence"] == 41
    assert anchor["attestation_id"] == "37747063"


def test_read_anchor_refuses_a_missing_file(tmp_path):
    missing = tmp_path / DEFAULT_ANCHOR_FILENAME
    with pytest.raises(AnchorError) as excinfo:
        read_anchor(missing)
    assert DEFAULT_ANCHOR_FILENAME in str(excinfo.value)


def test_read_anchor_refuses_a_non_object(tmp_path):
    with pytest.raises(AnchorError):
        read_anchor(_write(tmp_path / DEFAULT_ANCHOR_FILENAME, json.dumps([_anchor()])))


def test_read_anchor_refuses_undecodable_bytes(tmp_path):
    path = tmp_path / DEFAULT_ANCHOR_FILENAME
    path.write_bytes(b"\xff\xfe\xfd")
    # The #107 lesson: a decode failure is a typed finding, never an escaped
    # UnicodeDecodeError. pytest.raises(AnchorError) would not catch one.
    with pytest.raises(AnchorError):
        read_anchor(path)


def test_read_anchor_refuses_a_wrong_schema_id(tmp_path):
    document = _anchor(schema="loop-engineer/verdict@1")
    with pytest.raises(AnchorError):
        read_anchor(_write(tmp_path / DEFAULT_ANCHOR_FILENAME, document))


def test_read_anchor_refuses_a_missing_chain_head(tmp_path):
    document = _anchor()
    del document["chain_head"]
    with pytest.raises(AnchorError):
        read_anchor(_write(tmp_path / DEFAULT_ANCHOR_FILENAME, document))


@pytest.mark.parametrize("overrides", [
    pytest.param({"sequence": -1}, id="negative-sequence"),
    pytest.param({"sequence": "41"}, id="stringly-sequence"),
])
def test_read_anchor_refuses_a_schema_invalid_but_json_valid_document(tmp_path, overrides):
    # Parses, carries the right schema id, carries a well-formed chain_head, and
    # violates anchor@1 elsewhere. Deliberately NOT importorskip-gated: mode parity
    # is the point, and gating it would let the fallback leg accept a document the
    # schema rejects (the S3 plan-lint mode-parity repair is the precedent).
    with pytest.raises(AnchorError):
        read_anchor(_write(tmp_path / DEFAULT_ANCHOR_FILENAME, _anchor(**overrides)))


@pytest.mark.parametrize("head", MALFORMED_HEADS)
def test_read_anchor_refuses_a_malformed_chain_head(tmp_path, head):
    with pytest.raises(AnchorError):
        read_anchor(_write(tmp_path / DEFAULT_ANCHOR_FILENAME, _anchor(chain_head=head)))


def test_read_anchor_refuses_an_anchor_under_a_loop_dir(tmp_path):
    # D2 made mechanical: an anchor inside the tree it certifies is gitignored here,
    # so an adopter would silently carry an anchor that never lands in a commit.
    inside = _write(tmp_path / ".loop" / DEFAULT_ANCHOR_FILENAME, _anchor())
    with pytest.raises(AnchorError) as excinfo:
        read_anchor(inside)
    assert ".loop" in str(excinfo.value)


def test_subject_name_is_pinned():
    assert SUBJECT_NAME == "loop-chain-head"


def test_subject_bytes_is_exactly_64_lowercase_hex_with_no_trailing_newline():
    payload = subject_bytes(HEAD)
    assert isinstance(payload, bytes)
    assert len(payload) == 64
    assert payload == payload.lower()
    assert not payload.endswith(b"\n")
    assert payload.decode("ascii") == HEAD


@pytest.mark.parametrize("head", MALFORMED_HEADS)
def test_subject_bytes_refuses_a_malformed_head(head):
    with pytest.raises(VerdictError):
        subject_bytes(head)


def test_subject_bytes_digest_is_not_the_head_itself():
    # The property that distinguishes a D1 attestation from the three already minted:
    # the subject digest is now sha256 OF the head's bytes, not the head. A consumer
    # can regenerate those bytes from the head alone, which is what makes
    # `gh attestation verify` runnable at all.
    assert hashlib.sha256(subject_bytes(HEAD)).hexdigest() != HEAD
