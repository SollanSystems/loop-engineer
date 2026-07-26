import json


def test_schema_id_and_predicate_type_are_pinned():
    from loop.verdict import PREDICATE_TYPE, VERDICT_SCHEMA_ID

    assert VERDICT_SCHEMA_ID == "loop-engineer/verdict@1"
    assert PREDICATE_TYPE == "urn:loop-engineer:verdict:1"


def test_schema_file_declares_the_matching_id():
    from loop._resources import schemas_dir
    from loop.verdict import VERDICT_SCHEMA_ID

    schema = json.loads((schemas_dir() / "verdict.schema.json").read_text(encoding="utf-8"))
    assert schema["$id"] == VERDICT_SCHEMA_ID
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_verdict_schema_is_not_a_contract_artifact():
    # SCHEMA_IDS is the contract-object tuple (manifest/state/tasks/terminal).
    # verdict@1 is a projection, not a contract object, and must stay out of it.
    from loop.contract import SCHEMA_IDS
    from loop.verdict import VERDICT_SCHEMA_ID

    assert VERDICT_SCHEMA_ID not in SCHEMA_IDS
