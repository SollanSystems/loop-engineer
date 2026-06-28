import importlib.util
import json
import pathlib

_spec = importlib.util.spec_from_file_location(
    "il", pathlib.Path(__file__).parent / "inspect_loop.py"
)
il = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(il)


def _make_good_loop(root: pathlib.Path) -> pathlib.Path:
    """A full repo-OS contract: SPEC/WORKFLOW/TASKS + state, all 7 terminal
    states named, independent verification, approval gates, false-completion
    defense (holdout / anti-cheat) and plan-then-execute."""
    loop = root / "good"
    (loop / ".loop").mkdir(parents=True)
    (loop / "SPEC.md").write_text(
        "# SPEC\n## Goal\nDo X.\n## Success Criteria\n"
        "1. coverage >= 80% (scripts/verify-full)\n"
        "## Evidence Rules\nEach criterion maps to a scripts/verify-* command.\n",
        encoding="utf-8",
    )
    (loop / "WORKFLOW.md").write_text(
        "# WORKFLOW\n## Approval Gates\nPause on destructive commands / secret access.\n"
        "## Repair Cap\nmax 2 attempts then replan.\n"
        "## Plan-then-execute\nPrecommit the execution graph for untrusted reads.\n"
        "## Terminal States\n"
        "Succeeded, FailedUnverifiable, FailedBlocked, FailedBudget, "
        "FailedSafety, FailedSpecGap, AbortedByHuman.\n",
        encoding="utf-8",
    )
    (loop / "TASKS.json").write_text(
        json.dumps({"tasks": [{"id": "T1", "verify": "scripts/verify-fast"}]}),
        encoding="utf-8",
    )
    (loop / ".loop" / "state.json").write_text(
        json.dumps({"state": "verify", "terminal_state": None}), encoding="utf-8"
    )
    (loop / "scripts").mkdir()
    (loop / "scripts" / "verify-full").write_text("#!/bin/sh\n", encoding="utf-8")
    (loop / "scripts" / "holdout_gate.py").write_text(
        "# holdout / anti-cheat false-completion defense\n", encoding="utf-8"
    )
    return loop


def _make_bad_loop(root: pathlib.Path) -> pathlib.Path:
    """A loop dir with no verification, no terminal-state taxonomy, no approval
    gates, no false-completion defense — a 'completed'-claiming loop."""
    loop = root / "bad"
    loop.mkdir(parents=True)
    (loop / "README.md").write_text(
        "# some agent loop\nIt runs and then it is done.\n", encoding="utf-8"
    )
    return loop


def test_good_loop_scores_high_no_gaps(tmp_path):
    # Arrange
    loop = _make_good_loop(tmp_path)
    # Act
    report = il.inspect_loop(str(loop))
    # Assert
    assert report["score"] >= 80
    assert report["terminal_states_covered"] == 7
    assert report["gaps"] == []
    assert report["verdict"] in ("strong", "ok")


def test_bad_loop_scores_low_with_flagged_gaps(tmp_path):
    # Arrange
    loop = _make_bad_loop(tmp_path)
    # Act
    report = il.inspect_loop(str(loop))
    # Assert
    assert report["score"] < 40
    assert report["terminal_states_covered"] < 7
    assert report["gaps"], "bad loop must flag specific gaps"
    assert report["verdict"] == "weak"


def test_bad_loop_flags_the_specific_missing_elements(tmp_path):
    # Arrange
    loop = _make_bad_loop(tmp_path)
    # Act
    report = il.inspect_loop(str(loop))
    gap_text = " ".join(report["gaps"]).lower()
    # Assert — the prime-directive misses are named, not generic
    assert "verification" in gap_text
    assert "terminal" in gap_text
    assert "false-completion" in gap_text or "false completion" in gap_text


def test_good_loop_scores_strictly_higher_than_bad(tmp_path):
    # Arrange
    good = _make_good_loop(tmp_path)
    bad = _make_bad_loop(tmp_path)
    # Act
    good_report = il.inspect_loop(str(good))
    bad_report = il.inspect_loop(str(bad))
    # Assert — direction is the load-bearing invariant
    assert good_report["score"] > bad_report["score"]


def test_report_lists_present_signals_for_good_loop(tmp_path):
    # Arrange
    loop = _make_good_loop(tmp_path)
    # Act
    report = il.inspect_loop(str(loop))
    present_text = " ".join(report["present"]).lower()
    # Assert
    assert "verification" in present_text
    assert "approval" in present_text


def test_inspect_is_read_only_over_target(tmp_path):
    # Arrange
    loop = _make_good_loop(tmp_path)
    before = {p.name for p in loop.rglob("*")}
    # Act
    il.inspect_loop(str(loop))
    # Assert — inspector never writes into the scanned target
    after = {p.name for p in loop.rglob("*")}
    assert before == after


def test_score_is_bounded_0_to_100(tmp_path):
    # Arrange
    good = _make_good_loop(tmp_path)
    bad = _make_bad_loop(tmp_path)
    # Act / Assert
    for loop in (good, bad):
        report = il.inspect_loop(str(loop))
        assert 0 <= report["score"] <= 100


def test_cli_emits_json_and_exit_code(tmp_path, capsys):
    # Arrange
    loop = _make_good_loop(tmp_path)
    # Act
    rc = il.main([str(loop)])
    out = capsys.readouterr().out
    parsed = json.loads(out)
    # Assert
    assert rc == 0
    assert parsed["score"] >= 80
    assert "gaps" in parsed and "present" in parsed


def test_cli_nonzero_exit_on_weak_loop(tmp_path):
    # Arrange
    loop = _make_bad_loop(tmp_path)
    # Act / Assert — a weak loop is a non-zero (actionable) verdict
    assert il.main([str(loop)]) != 0


def test_deep_tree_is_not_descended_into(tmp_path):
    # Arrange — a directory chain deeper than the depth bound (>3 parts)
    loop = tmp_path / "deep"
    deep = loop / "a" / "b" / "c" / "d" / "e"
    deep.mkdir(parents=True)
    (deep / "buried.md").write_text("buriedneedle terminal\n", encoding="utf-8")
    # Act
    corpus = il._gather_corpus(loop)
    # Assert — content below the depth bound never reaches the corpus
    assert "buriedneedle" not in corpus


def test_deep_tree_walk_is_bounded_at_iteration_time(tmp_path, monkeypatch):
    # Arrange — instrument os.scandir so we can prove the deep dir is never
    # enumerated (the bound is applied while walking, not via rglob+post-filter,
    # which would scandir the whole tree first).
    import os

    loop = tmp_path / "deep"
    deep = loop / "a" / "b" / "c" / "d" / "e"
    deep.mkdir(parents=True)
    (deep / "buried.md").write_text("buried\n", encoding="utf-8")

    scanned: list[str] = []
    real_scandir = os.scandir

    def _spy_scandir(path=".", *a, **k):
        try:
            rel = pathlib.Path(os.fspath(path)).relative_to(loop)
            scanned.append("." if str(rel) == "." else str(rel))
        except ValueError:
            pass
        return real_scandir(path, *a, **k)

    monkeypatch.setattr(os, "scandir", _spy_scandir)
    # Act
    il._gather_corpus(loop)
    # Assert — directories deeper than the depth bound are never scandir'd
    assert not any(s.count("/") >= 3 for s in scanned), scanned


def test_oversized_file_is_not_fully_read(tmp_path):
    # Arrange — a file far larger than any contract file, with a sentinel at the tail
    loop = tmp_path / "big"
    loop.mkdir()
    big = loop / "huge.md"
    big.write_text(("x" * (2 * 1024 * 1024)) + "\ntailsentinel terminal\n", encoding="utf-8")
    # Act
    corpus = il._gather_corpus(loop)
    # Assert — the read is capped, so the tail content never reaches the corpus
    assert "tailsentinel" not in corpus


def test_read_text_honors_size_cap(tmp_path):
    # Arrange
    f = tmp_path / "f.txt"
    f.write_text("y" * (5 * 1024 * 1024), encoding="utf-8")
    # Act
    text = il._read_text(f)
    # Assert — never returns more than the cap
    assert len(text) <= il._MAX_READ_BYTES
