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
    # Invocation evidence: a verify-* gate actually runs the holdout gate, so the
    # defense earns FULL credit (the mere script file alone would earn nothing).
    (loop / "scripts" / "verify-safety").write_text(
        "#!/bin/sh\npython3 scripts/holdout_gate.py --strict\n", encoding="utf-8"
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


def test_read_text_honors_size_cap(tmp_path):
    # Arrange
    f = tmp_path / "f.txt"
    f.write_text("y" * (5 * 1024 * 1024), encoding="utf-8")
    # Act
    text = il._read_text(f)
    # Assert — never returns more than the cap
    assert len(text) <= il._MAX_READ_BYTES


def test_keyword_stuffed_readme_cannot_score_strong(tmp_path):
    # Arrange — all scoring keywords in one prose file, but no contract-owned
    # artifacts (SPEC/TASKS/WORKFLOW/scripts/.loop). This was the Opus-identified
    # exploit: substring stuffing could previously score 100/strong.
    loop = tmp_path / "stuffed"
    loop.mkdir()
    (loop / "README.md").write_text(
        "success criteria verify-fast approval gate holdout anticheat "
        "plan-then-execute Succeeded FailedUnverifiable FailedBlocked "
        "FailedBudget FailedSafety FailedSpecGap AbortedByHuman\n",
        encoding="utf-8",
    )

    # Act
    report = il.inspect_loop(str(loop))

    # Assert — prose-only keyword stuffing is not a valid loop contract.
    assert report["verdict"] == "weak"
    assert report["score"] < 50
    assert any("contract" in gap.lower() or "SPEC.md" in gap for gap in report["gaps"])


def test_manifest_false_plan_then_execute_does_not_get_credit(tmp_path):
    # Arrange — a structurally valid loop whose manifest explicitly sets
    # plan_then_execute false. The inspector must read the boolean, not credit the
    # mere string "plan_then_execute" appearing in manifest YAML.
    loop = _make_good_loop(tmp_path)
    (loop / ".loop" / "manifest.yaml").write_text(
        "schema: loop-engineer/manifest@1\n"
        "loop: sample\n"
        "policies:\n"
        "  plan_then_execute: false\n"
        "  verifier_gaming: hard_terminate_as_security_failure\n"
        "terminal_states:\n"
        "  - Succeeded\n"
        "  - FailedUnverifiable\n"
        "  - FailedBlocked\n"
        "  - FailedBudget\n"
        "  - FailedSafety\n"
        "  - FailedSpecGap\n"
        "  - AbortedByHuman\n",
        encoding="utf-8",
    )

    # Act
    report = il.inspect_loop(str(loop))
    present_text = " ".join(report["present"]).lower()
    gap_text = " ".join(report["gaps"]).lower()

    # Assert
    assert "plan-then-execute" not in present_text
    assert "plan-then-execute" in gap_text


# --- false-completion defense requires invocation evidence -----------------


def test_bare_terminal_flag_earns_no_defense_credit(tmp_path):
    # A self-asserted `false_completion: false` in terminal_state.json is a
    # claim, not evidence — it must earn ZERO false-completion-defense credit.
    loop = tmp_path / "flagonly"
    (loop / ".loop").mkdir(parents=True)
    (loop / ".loop" / "terminal_state.json").write_text(
        json.dumps({"false_completion": False}), encoding="utf-8"
    )

    report = il.inspect_loop(str(loop))
    present = " ".join(report["present"]).lower()
    gaps = " ".join(report["gaps"]).lower()

    assert "false-completion defense" not in present
    assert "no recorded holdout/anti-cheat invocation" in gaps


def test_defense_credit_requires_invocation_evidence(tmp_path):
    # Graded credit: a recorded invocation earns FULL credit, a wired-but-unrun
    # gate earns PARTIAL, and a bare prose mention earns ZERO. All three share an
    # identical base (a verify-fast gate) so only the defense signal varies.
    def _base(name):
        d = tmp_path / name
        (d / "scripts").mkdir(parents=True)
        (d / "scripts" / "verify-fast").write_text("#!/bin/sh\n", encoding="utf-8")
        return d

    # FULL — a verify-* script invokes the holdout gate on an executable line.
    full = _base("full")
    (full / "scripts" / "holdout_gate.py").write_text("# gate\n", encoding="utf-8")
    (full / "scripts" / "verify-safety").write_text(
        "#!/bin/sh\npython3 scripts/holdout_gate.py --strict\n", encoding="utf-8"
    )
    full_report = il.inspect_loop(str(full))

    # WIRED — the gate script exists and is referenced from the verify surface,
    # but nothing recorded a run of it.
    wired = _base("wired")
    (wired / "scripts" / "holdout_gate.py").write_text("# gate\n", encoding="utf-8")
    (wired / "WORKFLOW.md").write_text(
        "# WORKFLOW\n## Anti-cheat\nHigh-value tasks are gated by "
        "scripts/holdout_gate.py.\n",
        encoding="utf-8",
    )
    wired_report = il.inspect_loop(str(wired))

    # PROSE — only a prose mention plus a self-asserted terminal flag; no script.
    prose = _base("prose")
    (prose / ".loop").mkdir()
    (prose / "WORKFLOW.md").write_text(
        "# WORKFLOW\nWe have false-completion defense and anti-cheat discipline.\n",
        encoding="utf-8",
    )
    (prose / ".loop" / "terminal_state.json").write_text(
        json.dumps({"false_completion": False}), encoding="utf-8"
    )
    prose_report = il.inspect_loop(str(prose))

    full_present = " ".join(full_report["present"]).lower()
    wired_present = " ".join(wired_report["present"]).lower()
    prose_present = " ".join(prose_report["present"]).lower()

    assert "false-completion defense (invoked)" in full_present
    assert "false-completion defense (wired, no recorded run)" in wired_present
    assert "false-completion defense" not in prose_present

    # Graded points: full > wired > zero (the only varying signal is defense).
    assert full_report["score"] > wired_report["score"] > prose_report["score"]


# --- dogfood regressions (inspector on 9 real loops, v0.3.4) ---------------


def _make_malformed_manifest_loop(root: pathlib.Path) -> pathlib.Path:
    """A foreign loop whose `.loop/manifest.yaml` is malformed YAML — the
    FoundersOS / LumenNotes shape that crashed the inspector (F1)."""
    loop = root / "malformed"
    (loop / ".loop").mkdir(parents=True)
    (loop / ".loop" / "manifest.yaml").write_text(
        "schema: loop-engineer/manifest@1\n"
        "policies:\n"
        "  - id: ci-change      ; trigger: edit .github/workflows/*\n",
        encoding="utf-8",
    )
    return loop


def test_inspect_loop_does_not_crash_on_malformed_manifest(tmp_path):
    # F1: the inspected loop is untrusted DATA; a malformed manifest must yield a
    # report, never a traceback.
    loop = _make_malformed_manifest_loop(tmp_path)
    report = il.inspect_loop(str(loop))  # must not raise
    assert "verdict" in report and "score" in report


def test_cli_emits_json_not_traceback_on_malformed_manifest(tmp_path, capsys):
    # F1: the CLI must print a JSON report, not exit with an uncaught traceback.
    loop = _make_malformed_manifest_loop(tmp_path)
    rc = il.main([str(loop)])
    out = capsys.readouterr().out
    parsed = json.loads(out)  # raises if the CLI crashed instead of reporting
    assert "verdict" in parsed
    assert rc in (0, 1)


def _make_dotloop_only_loop(root: pathlib.Path) -> pathlib.Path:
    """A real-shaped loop whose contract files live under `.loop/` (SPEC,
    WORKFLOW, TASKS) — like the loop-engineer repo itself — not at the workspace
    root. (F2)"""
    loop = root / "dotloop"
    dl = loop / ".loop"
    dl.mkdir(parents=True)
    (dl / "SPEC.md").write_text(
        "# SPEC\n## Success Criteria\n1. fast gate passes (scripts/verify-fast)\n",
        encoding="utf-8",
    )
    (dl / "WORKFLOW.md").write_text(
        "# WORKFLOW\n## Approval Gates\nPause on destructive commands.\n"
        "## Plan-then-execute\nPrecommit the execution graph for untrusted reads.\n"
        "## Terminal States\n"
        "Succeeded, FailedUnverifiable, FailedBlocked, FailedBudget, "
        "FailedSafety, FailedSpecGap, AbortedByHuman.\n",
        encoding="utf-8",
    )
    (dl / "TASKS.json").write_text(
        json.dumps({"tasks": [{"id": "T1", "verify": "scripts/verify-fast"}]}),
        encoding="utf-8",
    )
    return loop


def test_inspect_credits_success_and_verify_from_dotloop_contract(tmp_path):
    # F2: SPEC/WORKFLOW/TASKS under .loop/ must be scored on substance, not
    # missed because they aren't at the workspace root.
    loop = _make_dotloop_only_loop(tmp_path)
    report = il.inspect_loop(str(loop))
    present = " ".join(report["present"]).lower()
    gaps = " ".join(report["gaps"]).lower()
    assert "defines verifiable success criteria" in present
    assert "independent verification" in present
    assert "no defined success criteria" not in gaps
    assert "no independent verification" not in gaps


def test_single_file_loop_contract_terminal_states_credited(tmp_path):
    # F4: a committed single-file `loop-contract.md` (the Quiet Command shape)
    # that names all 7 terminal states must score 7/7, not 0/7.
    loop = tmp_path / "cmd"
    loop.mkdir()
    (loop / "loop-contract.md").write_text(
        "# Loop Contract\n## Terminal States\n"
        "Succeeded, FailedUnverifiable, FailedBlocked, FailedBudget, "
        "FailedSafety, FailedSpecGap, AbortedByHuman\n",
        encoding="utf-8",
    )
    report = il.inspect_loop(str(loop))
    assert report["terminal_states_covered"] == 7


def test_no_unwired_corpus_scoring_helpers():
    # F3: the broad-substring corpus scoring path was abandoned for the typed-
    # contract path (the keyword-stuffing fix). Its helpers must not linger as
    # dead code that silently re-diverges from the SKILL's documented behavior.
    for name in ("_evaluate_checks", "_terminal_states_covered", "_gather_corpus", "_walk_bounded"):
        assert not hasattr(il, name), f"{name} is dead code — wire it into inspect_loop or delete it"


def test_documented_cli_by_path_reads_dotloop_manifest(tmp_path):
    # Regression: run via `python3 scripts/inspect_loop.py <loop>` (sys.path[0]
    # is scripts/, not the repo root). Without a self-bootstrap, the real
    # loop.contract.read_manifest is unimportable and the degraded fallback stub
    # returns None — so the inspector cannot read `plan_then_execute: false` from
    # `.loop/manifest.yaml` and instead substring-credits the "Plan-then-execute"
    # heading in WORKFLOW.md. Exec by path with PYTHONPATH scrubbed to reproduce.
    import os
    import subprocess
    import sys

    loop = _make_good_loop(tmp_path)
    (loop / ".loop" / "manifest.yaml").write_text(
        "schema: loop-engineer/manifest@1\n"
        "loop: sample\n"
        "policies:\n"
        "  plan_then_execute: false\n"
        "  verifier_gaming: hard_terminate_as_security_failure\n"
        "terminal_states:\n"
        "  - Succeeded\n"
        "  - FailedUnverifiable\n"
        "  - FailedBlocked\n"
        "  - FailedBudget\n"
        "  - FailedSafety\n"
        "  - FailedSpecGap\n"
        "  - AbortedByHuman\n",
        encoding="utf-8",
    )

    script = pathlib.Path(__file__).parent / "inspect_loop.py"
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    proc = subprocess.run(
        [sys.executable, str(script), str(loop)],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        env=env,
    )

    # 0 (not weak) or 1 (weak) are both valid runs; anything else is a crash.
    assert proc.returncode in (0, 1), proc.stderr
    report = json.loads(proc.stdout)
    present_text = " ".join(report["present"]).lower()
    gap_text = " ".join(report["gaps"]).lower()
    assert "plan-then-execute" not in present_text, report
    assert "plan-then-execute" in gap_text, report


# --- M3: false-completion credit grades on execution evidence, not tokens ----


def _verify_gate_loop(root: pathlib.Path, name: str, verify_body: str) -> pathlib.Path:
    """A loop whose only signal is a single verify-safety script body."""
    d = root / name
    (d / "scripts").mkdir(parents=True)
    (d / "scripts" / "verify-safety").write_text(
        "#!/bin/sh\n" + verify_body, encoding="utf-8"
    )
    return d


def test_string_literal_gate_tokens_earn_no_invoked_credit(tmp_path):
    # M3(a): a token inside echo/printf/':' args (or any quoted-string emit) is
    # inert output, not an executed gate — it must earn ZERO invoked credit.
    exploits = (
        'echo "holdout_gate"\n',
        "printf 'holdout_gate\\n'\n",
        ": holdout_gate\n",
        'echo "run the holdout_gate please"\n',
        'echo "holdout_gate.py"\n',  # even the script name, still just printed
    )
    for i, body in enumerate(exploits):
        loop = _verify_gate_loop(tmp_path, f"exploit{i}", body)
        assert il._gate_invoked_in_verify(loop) is False, body


def test_real_gate_invocations_keep_invoked_credit(tmp_path):
    # M3(a): the token as part of a genuinely invoked command keeps full credit.
    real = (
        "python3 scripts/holdout_gate.py --strict\n",
        "bash scripts/anticheat_scan.py\n",
        "./scripts/holdout_gate.py\n",
        "uv run python scripts/anticheat_scan.py\n",
        # the flagship shape: the gate path is double-quoted, invoked by python3.
        'python3 "$REPO/scripts/holdout_gate.py" "$EX/target/manifest.json" --cwd "$EX/target"\n',
        # chained after an echo — the real invocation must still count.
        'echo "gate:" && python3 scripts/holdout_gate.py\n',
    )
    for i, body in enumerate(real):
        loop = _verify_gate_loop(tmp_path, f"real{i}", body)
        assert il._gate_invoked_in_verify(loop) is True, body


def test_bare_gate_token_in_runlog_earns_no_recorded_credit(tmp_path):
    # M3(b): a bare gate token in RUNLOG prose is a self-narration, not a run —
    # even when the token itself (anticheat_scan) contains a run-word ("scan").
    loop = tmp_path / "rl"
    (loop / ".loop").mkdir(parents=True)
    (loop / "RUNLOG.md").write_text(
        "This loop uses holdout_gate and anticheat_scan for false-completion defense.\n",
        encoding="utf-8",
    )
    paths = il.resolve_loop_paths(loop)
    assert il._gate_run_recorded(paths) is False


def test_recorded_gate_run_with_run_word_earns_credit(tmp_path):
    # M3(b): a real recorded run — token AND an independent run-word on one line.
    loop = tmp_path / "rl2"
    (loop / ".loop").mkdir(parents=True)
    (loop / "RUNLOG.md").write_text(
        "gate: scripts/holdout_gate.py target/manifest.json -> verdict Succeeded\n",
        encoding="utf-8",
    )
    paths = il.resolve_loop_paths(loop)
    assert il._gate_run_recorded(paths) is True


def test_receipts_jsonl_records_gate_run(tmp_path):
    # M3(b): a structured receipt line is parsed as JSON and matched on fields.
    loop = tmp_path / "rc"
    (loop / ".loop" / "receipts").mkdir(parents=True)
    (loop / ".loop" / "receipts" / "run.jsonl").write_text(
        json.dumps({"event": "holdout_gate", "verdict": "Succeeded"}) + "\n",
        encoding="utf-8",
    )
    paths = il.resolve_loop_paths(loop)
    assert il._gate_run_recorded(paths) is True


def test_prose_renamed_to_jsonl_earns_no_recorded_credit(tmp_path):
    # M3(b): a non-JSON prose line stuffed into a .jsonl file is not a receipt.
    loop = tmp_path / "rc2"
    (loop / ".loop" / "receipts").mkdir(parents=True)
    (loop / ".loop" / "receipts" / "run.jsonl").write_text(
        "holdout_gate anticheat_scan verdict clean passed\n", encoding="utf-8"
    )
    paths = il.resolve_loop_paths(loop)
    assert il._gate_run_recorded(paths) is False


def test_stuffed_fake_without_gate_file_cannot_reach_wired(tmp_path):
    # M3(c): file-exists + surface-reference is the wired bar; with NO gate script
    # file, a stuffed contract that merely names the gate cannot reach "wired".
    loop = tmp_path / "nofile"
    (loop / "scripts").mkdir(parents=True)
    (loop / "WORKFLOW.md").write_text(
        "# WORKFLOW\nHigh-value tasks are gated by scripts/holdout_gate.py anti-cheat.\n",
        encoding="utf-8",
    )
    (loop / "SPEC.md").write_text(
        "# SPEC\nholdout_gate anticheat_scan anti-cheat defense.\n", encoding="utf-8"
    )
    paths = il.resolve_loop_paths(loop)
    assert il._gate_script_referenced(paths) is False
    assert il._false_completion_credit(paths) == "none"


def test_flagship_example_keeps_strong_gate_backed_verdict():
    # Regression guard: the genuinely gate-backed flagship must keep its verdict
    # and its invoked false-completion credit — the discriminator must not dock
    # the real, double-quoted `holdout_gate.py` invocation in its verify-full.
    root = pathlib.Path(__file__).resolve().parent.parent
    report = il.inspect_loop(str(root / "examples" / "coverage-repair"))
    assert report["verdict"] == "strong"
    assert report["score"] >= 80
    assert any("invoked" in signal for signal in report["present"])


# --- M2: unfilled scaffold placeholders earn no defines_success credit --------


def test_placeholder_success_criteria_earn_no_defines_success_credit(tmp_path):
    loop = tmp_path / "ph"
    loop.mkdir()
    (loop / "SPEC.md").write_text(
        "# SPEC\n## Success criteria\n"
        "1. REPLACE: first success criterion\n2. REPLACE\n3. REPLACE\n",
        encoding="utf-8",
    )
    report = il.inspect_loop(str(loop))
    present = " ".join(report["present"]).lower()
    gaps = " ".join(report["gaps"]).lower()
    assert "defines verifiable success criteria" not in present
    # The gap names the scaffold placeholder convention actionably.
    assert "replace" in gaps and "placeholder" in gaps


def test_real_success_criteria_still_earn_defines_success_credit(tmp_path):
    loop = tmp_path / "real"
    loop.mkdir()
    (loop / "SPEC.md").write_text(
        "# SPEC\n## Success criteria\n1. coverage >= 80% (scripts/verify-full)\n",
        encoding="utf-8",
    )
    report = il.inspect_loop(str(loop))
    present = " ".join(report["present"]).lower()
    assert "defines verifiable success criteria" in present


def test_one_filled_criterion_among_placeholders_still_earns_credit(tmp_path):
    # Partial fill is real intent — a single concrete criterion keeps the credit.
    loop = tmp_path / "partial"
    loop.mkdir()
    (loop / "SPEC.md").write_text(
        "# SPEC\n## Success criteria\n"
        "1. coverage >= 80% (scripts/verify-full)\n2. REPLACE\n",
        encoding="utf-8",
    )
    report = il.inspect_loop(str(loop))
    present = " ".join(report["present"]).lower()
    assert "defines verifiable success criteria" in present


def test_placeholder_task_titles_flagged_as_gap(tmp_path):
    loop = tmp_path / "pht"
    loop.mkdir()
    (loop / "TASKS.json").write_text(
        json.dumps({"tasks": [{"id": "T1", "title": "REPLACE: first task",
                               "verify": "scripts/verify-fast"}]}),
        encoding="utf-8",
    )
    report = il.inspect_loop(str(loop))
    gaps = " ".join(report["gaps"]).lower()
    assert "task" in gaps and "placeholder" in gaps


def test_fresh_scaffold_is_not_strong_with_placeholder_gaps(tmp_path):
    # M2: an unedited scaffold scored 86/strong; it must now land at ok-or-below
    # and name the placeholder convention so a stranger knows what to fill.
    from loop.scaffold import scaffold

    target = tmp_path / "fresh-scaffold"
    scaffold(target)
    report = il.inspect_loop(str(target))
    gaps = " ".join(report["gaps"]).lower()

    assert report["verdict"] != "strong"
    assert report["score"] < 80
    assert "replace" in gaps and "placeholder" in gaps


def test_keyword_stuffed_fake_scores_below_strong_with_false_completion_gap(tmp_path):
    # Acceptance (M2 + M3): the review's keyword-stuffed fake — SPEC/WORKFLOW
    # prose stuffed with checklist vocabulary, all 7 terminal states, an echo
    # "verify" line, a stuffed RUNLOG, and NO real gate files. It scored
    # 100/strong before the fixes; it must now land materially below strong with
    # a false-completion gap (the echo trick and stuffed prose buy no defense
    # credit — M3 — and the unfilled success criteria earn no defines_success
    # credit — M2).
    fake = tmp_path / "fake"
    (fake / ".loop").mkdir(parents=True)
    (fake / "scripts").mkdir()
    (fake / "SPEC.md").write_text(
        "# SPEC — totally-done\n"
        "This loop has verifiable success, independent verification, approval "
        "gates, false-completion defense, held-out anti-cheat, plan-then-execute.\n"
        "## Success criteria\n"
        "1. REPLACE: first success criterion\n"
        "2. REPLACE\n",
        encoding="utf-8",
    )
    (fake / "WORKFLOW.md").write_text(
        "# WORKFLOW\n## Approval Gates\nApproval gate on side-effects.\n"
        "## Plan-then-execute\nPlan-then-execute for untrusted reads.\n"
        "## Anti-cheat\nfalse-completion defense via held-out holdout gate anti-cheat.\n"
        "## Terminal States\n"
        "Succeeded, FailedUnverifiable, FailedBlocked, FailedBudget, "
        "FailedSafety, FailedSpecGap, AbortedByHuman.\n",
        encoding="utf-8",
    )
    (fake / "TASKS.json").write_text(
        json.dumps({"tasks": [{"id": "T1", "title": "REPLACE: first task",
                               "verify": "scripts/verify-fast"}]}),
        encoding="utf-8",
    )
    (fake / "scripts" / "verify-fast").write_text(
        '#!/bin/sh\necho "holdout_gate anticheat_scan all clean"\n', encoding="utf-8"
    )
    (fake / "RUNLOG.md").write_text(
        "Iteration 1: holdout gate anti-cheat false-completion defense engaged. "
        "Everything looks done and fine.\n",
        encoding="utf-8",
    )

    report = il.inspect_loop(str(fake))
    present = " ".join(report["present"]).lower()
    gaps = " ".join(report["gaps"]).lower()

    assert "false-completion defense" not in present
    assert "false-completion" in gaps or "false completion" in gaps
    assert report["verdict"] != "strong"
    assert report["score"] < 80
