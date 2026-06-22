import importlib.util
import pathlib

_spec = importlib.util.spec_from_file_location(
    "hg", pathlib.Path(__file__).parent / "holdout_gate.py"
)
hg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hg)


def _r(id_, passed):
    return {"id": id_, "passed": passed}


def test_succeeded_requires_holdout_green():
    v = hg.decide([_r("a", True)], [_r("h", True)])
    assert v["verdict"] == "Succeeded"
    assert v["passed_visible"] and v["passed_holdout"]
    assert v["false_completion"] is False


def test_visible_pass_holdout_fail_is_false_completion():
    v = hg.decide([_r("a", True)], [_r("h", False)])
    assert v["verdict"] == "FailedUnverifiable"
    assert v["false_completion"] is True


def test_visible_fail_is_not_ready_not_false_completion():
    v = hg.decide([_r("a", False)], [_r("h", True)])
    assert v["verdict"] == "NotReady"
    assert v["false_completion"] is False


def test_empty_holdout_cannot_certify():
    v = hg.decide([_r("a", True)], [])
    assert v["verdict"] == "NotReady"
    assert "holdout" in v["reason"]
    assert v["false_completion"] is False


def test_run_manifest_executes_commands():
    manifest = {
        "visible": [{"id": "v", "cmd": "true"}],
        "holdout": [{"id": "h", "cmd": "true"}],
    }
    assert hg.run_manifest(manifest)["verdict"] == "Succeeded"


def test_run_manifest_detects_false_completion_via_exit_codes():
    manifest = {
        "visible": [{"id": "v", "cmd": "true"}],
        "holdout": [{"id": "h", "cmd": "false"}],
    }
    out = hg.run_manifest(manifest)
    assert out["verdict"] == "FailedUnverifiable"
    assert out["false_completion"] is True


def test_main_exit_code_nonzero_when_not_succeeded(tmp_path):
    import json

    m = tmp_path / "m.json"
    m.write_text(json.dumps({
        "visible": [{"id": "v", "cmd": "true"}],
        "holdout": [{"id": "h", "cmd": "false"}],
    }))
    assert hg.main([str(m)]) == 1
