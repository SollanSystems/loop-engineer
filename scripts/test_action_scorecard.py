# scripts/test_action_scorecard.py
"""Gate-strictness acceptance for the shipped GitHub Action.

F3 — the composite action must install loop-engineer WITH its schema extras on
both install paths, so `loop doctor` runs real JSON-Schema validation (not the
pure-stdlib structural fallback) and asserts as much. F8 — the scorecard logic
is extracted into scripts/action_scorecard.py so it validates fail-under as an
integer instead of tracebacking on non-numeric input, and the PR comment is
sticky (edit-in-place, never a fresh comment per run)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
ACTION_YML = REPO_ROOT / "action.yml"


def _scorecard():
    """Import the extracted scorecard module lazily so the action-wiring tests
    stay independent of it existing yet (TDD)."""
    sys.path.insert(0, str(SCRIPTS_DIR))
    import action_scorecard  # type: ignore

    return action_scorecard


def _action() -> dict:
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(ACTION_YML.read_text(encoding="utf-8"))


def _steps() -> list[dict]:
    return _action()["runs"]["steps"]


def _step(name_fragment: str) -> dict:
    for step in _steps():
        if name_fragment.lower() in str(step.get("name", "")).lower():
            return step
    raise AssertionError(f"no action step whose name contains {name_fragment!r}")


def test_action_yml_is_valid_yaml():
    action = _action()
    assert action["runs"]["using"] == "composite"


# --- F3: strict-by-install on the action gate surface ------------------------


def test_both_install_paths_carry_the_schema_extras():
    run = _step("Install loop-engineer")["run"]
    # PyPI-pinned path and the action-checkout path must both request the extras.
    assert 'loop-engineer[schemas,yaml]==' in run, (
        "the versioned PyPI install must request the [schemas,yaml] extras"
    )
    assert '}}[schemas,yaml]' in run or 'github.action_path }}[schemas,yaml]' in run, (
        "the action-checkout install must request the [schemas,yaml] extras"
    )


def test_bare_install_without_extras_is_gone():
    run = _step("Install loop-engineer")["run"]
    assert '"loop-engineer==' not in run, "bare (extras-free) PyPI install path lingers"
    # the action-path install must not appear without the extras suffix
    assert '"${{ github.action_path }}"' not in run, (
        "bare (extras-free) action-checkout install path lingers"
    )


def test_doctor_step_asserts_jsonschema_validation_mode():
    run = _step("loop doctor")["run"]
    assert "validation_mode" in run, (
        "the doctor step should assert the report's validation_mode is jsonschema "
        "so a packaging regression that drops the extras fails loudly"
    )
    assert "jsonschema" in run


# --- F8: robust, tested scorecard logic --------------------------------------


def test_parse_fail_under_accepts_valid_integers():
    sc = _scorecard()
    assert sc.parse_fail_under("0") == 0
    assert sc.parse_fail_under("80") == 80
    assert sc.parse_fail_under("100") == 100


@pytest.mark.parametrize("bad", ["80.5", "abc", "", "-1", "101", " "])
def test_parse_fail_under_rejects_non_integers_and_out_of_range(bad):
    sc = _scorecard()
    with pytest.raises(ValueError):
        sc.parse_fail_under(bad)


def test_render_summary_embeds_sticky_marker_and_scorecard_fields():
    sc = _scorecard()
    out = sc.render_summary({"score": 72, "verdict": "strong", "gaps": ["g1", "g2"]})
    assert sc.MARKER in out
    assert "loop-engineer scorecard" in out
    assert "72/100" in out
    assert "**strong**" in out
    assert "- g1" in out and "- g2" in out


def test_render_summary_caps_gap_list_at_ten():
    sc = _scorecard()
    out = sc.render_summary({"score": 0, "verdict": "weak", "gaps": [f"g{i}" for i in range(20)]})
    assert "- g9" in out
    assert "- g10" not in out


def _run_main(sc, argv, tmp_path, monkeypatch):
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))
    return sc.main(argv)


def test_main_non_numeric_fail_under_is_distinct_exit_and_clear_error(tmp_path, monkeypatch, capsys):
    sc = _scorecard()
    inspect = tmp_path / "inspect.json"
    inspect.write_text(json.dumps({"score": 90, "verdict": "strong"}), encoding="utf-8")
    rc = _run_main(sc, [str(inspect), "80.5"], tmp_path, monkeypatch)
    out = capsys.readouterr().out
    assert rc == 2, "bad fail-under must use a distinct exit code, not the fail-under-breach code"
    assert "::error::" in out
    assert "80.5" in out


def test_main_weak_verdict_warns_but_passes_when_fail_under_zero(tmp_path, monkeypatch, capsys):
    sc = _scorecard()
    inspect = tmp_path / "inspect.json"
    inspect.write_text(json.dumps({"score": 40, "verdict": "weak", "gaps": []}), encoding="utf-8")
    rc = _run_main(sc, [str(inspect), "0"], tmp_path, monkeypatch)
    out = capsys.readouterr().out
    assert rc == 0
    assert "::warning::" in out


def test_main_fail_under_breach_exits_one_with_error(tmp_path, monkeypatch, capsys):
    sc = _scorecard()
    inspect = tmp_path / "inspect.json"
    inspect.write_text(json.dumps({"score": 50, "verdict": "strong", "gaps": []}), encoding="utf-8")
    rc = _run_main(sc, [str(inspect), "80"], tmp_path, monkeypatch)
    out = capsys.readouterr().out
    assert rc == 1
    assert "::error::" in out


def test_main_writes_step_summary_and_scorecard_with_marker(tmp_path, monkeypatch):
    sc = _scorecard()
    inspect = tmp_path / "inspect.json"
    inspect.write_text(json.dumps({"score": 88, "verdict": "strong", "gaps": ["x"]}), encoding="utf-8")
    rc = _run_main(sc, [str(inspect), "0"], tmp_path, monkeypatch)
    assert rc == 0
    scorecard_md = (tmp_path / "scorecard.md").read_text(encoding="utf-8")
    summary_md = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert sc.MARKER in scorecard_md
    assert sc.MARKER in summary_md
    assert "88/100" in scorecard_md


def test_main_wrong_argument_count_returns_two(tmp_path, monkeypatch, capsys):
    sc = _scorecard()
    rc = _run_main(sc, ["only-one-arg"], tmp_path, monkeypatch)
    capsys.readouterr()
    assert rc == 2


def test_main_malformed_inspect_json_returns_two(tmp_path, monkeypatch, capsys):
    sc = _scorecard()
    inspect = tmp_path / "inspect.json"
    inspect.write_text("not json", encoding="utf-8")
    rc = _run_main(sc, [str(inspect), "0"], tmp_path, monkeypatch)
    capsys.readouterr()
    assert rc == 2


# --- F8: action wiring -------------------------------------------------------


def test_scorecard_step_invokes_the_extracted_script():
    run = _step("loop inspect")["run"]
    assert "action_scorecard.py" in run, "the scorecard step must call the extracted script"


def test_no_fragile_inline_scorecard_python_remains():
    text = ACTION_YML.read_text(encoding="utf-8")
    assert "int(sys.argv[2])" not in text, (
        "the fragile inline int(sys.argv[2]) scorecard heredoc must be gone"
    )


def test_pr_comment_step_is_sticky():
    run = _step("PR scorecard comment")["run"]
    assert "loop-engineer-scorecard" in run, "the comment step must look up the marker comment"
    assert "PATCH" in run, "the comment step must edit the existing marker comment in place"
    assert "warning" in run.lower(), "the comment step must stay non-fatal on API failure"
