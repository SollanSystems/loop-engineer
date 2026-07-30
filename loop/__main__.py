from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from .contract import VALIDATION_MODES, ContractIssue, ValidationModeError, doctor_report
from .plan import validate_plan
from .runtime import RuntimeStoreError, replay_report, status_report
from .runcontrol import RunControlError

_PROG = "python3 -m loop"

_COMMANDS = ("scaffold", "doctor", "validate", "verify", "verdict", "inspect", "metrics", "plan-lint", "status", "replay", "simulate", "run", "approve", "pause", "resume", "cancel", "migrate", "architect")

# Read commands operate on an EXISTING contract dir; scaffold CREATES one, so it
# is exempt from the "target must exist" guard.
_READ_COMMANDS = ("doctor", "validate", "verify", "verdict", "inspect", "metrics", "plan-lint", "status", "replay", "simulate", "run", "approve", "pause", "resume", "cancel", "migrate")

_USAGE = f"usage: {_PROG} <scaffold|doctor|validate|verify|verdict|inspect|metrics|plan-lint|status|replay|simulate|run|approve|pause|resume|cancel|migrate|architect> <target>"

_HELP = f"""{_PROG} — validate, inspect, and measure a portable repo-OS loop contract.

{_USAGE}
       {_PROG} metrics [--baseline] <workspace-or-.loop>
       {_PROG} doctor|validate|verify [--mode basic|strict|release]
              [--expect-chain-head SHA256]
              [--expect-chain-ancestor SHA256 | --anchor PATH] <workspace-or-.loop>
       {_PROG} verdict [--mode basic|strict|release]
              [--compare FILE|- | --emit-subject] <workspace>
       {_PROG} status [--mode basic|strict|release] <workspace>
       {_PROG} replay [--mode basic|strict|release] <workspace>
       {_PROG} simulate [--mode basic|strict|release] <workspace>
       {_PROG} run [--mode basic|strict|release] <workspace>
       {_PROG} approve --decision approved|denied [--resume-target STATE] [--mode basic|strict|release] <workspace>
       {_PROG} pause --reason REASON [--mode basic|strict|release] <workspace>
       {_PROG} resume [--note NOTE] [--mode basic|strict|release] <workspace>
       {_PROG} cancel [--reason REASON] [--mode basic|strict|release] <workspace>
       {_PROG} migrate <workspace>
       {_PROG} plan-lint [--mode basic|strict|release] <plan-file>

commands:
  scaffold   Write a fresh, doctor-clean loop contract into <target>.
  doctor     Validate the contract objects; --mode selects validation strength.
  validate   Alias for doctor.
  verify     Alias for doctor — check the contract's state.
  verdict    Emit the predicate body only; the signer (actions/attest) constructs
             the in-toto Statement. Never signs and never verifies a signature.
             (schema loop-engineer/verdict@1: doctor status, chain head, terminal outcome, verified-evidence digests)
  inspect    Score an existing loop against the prime-directive checklist
             (emits a weak/strong verdict and a gap report).
  metrics    Derive false-completion-rate + repair-productivity from the loop's
             real .loop/ evidence (RUNLOG, verify bundles, held-out gate, repair
             records) and emit a JSON scorecard. With --baseline, write a
             checked-in baseline scorecard — refused unless the run is gate-backed.
  plan-lint  Validate a loop-engineer/plan@1 Loop Plan IR document: task-kind
             fields, dependency-graph acyclicity, and the terminal-state
             mapping. --mode selects validation strength, same as doctor.
  status     Project the read-only event log and reconcile it with state.json.
  replay     Double-fold the read-only event log and check terminal synchronization.
  simulate   Strictly read-only dry-run: report what the next run step would do.
  run        Perform one event-sourced execute-task dispatch step.
  approve    Resolve a pending approval request.
  pause      Pause a non-terminal run.
  resume     Resume a paused run.
  cancel     Terminate a non-terminal run as AbortedByHuman.
  migrate    Add hash-chain columns to a legacy events.db (explicit, idempotent; the only store-upgrade path).
  architect  Not implemented by this CLI: architecture classification and ADR
             authorship require agentic judgment, not deterministic code. See
             the loop-architect skill.

arguments:
  <target>     A workspace root or its .loop/ directory (all commands except plan-lint).
  <plan-file>  A single loop-engineer/plan@1 JSON file (plan-lint only).

options:
  --mode {{basic,strict,release}}
                (doctor/validate/verify/verdict/plan-lint/status/replay/simulate/run) basic forces structural
                checks; strict/release require jsonschema. Default: auto-detect.
  --expect-chain-head SHA256
                (doctor/validate/verify) fail unless the event store's chain head
                is exactly this 64-character lowercase hex hash. A missing,
                unreadable, unchained, or diverged store fails the gate.
  --expect-chain-ancestor SHA256
                (doctor/validate/verify) fail unless this digest WAS the chain head
                at some sequence, established by replaying and recomputing every
                hash — never by trusting the stored event_hash column. Use this
                across runs: exact head equality fails by construction once the
                store grows. Composes with --expect-chain-head.
  --anchor PATH (doctor/validate/verify) resolve --expect-chain-ancestor from a
                tracked loop-engineer/anchor@1 file (conventionally
                loop-anchor.json, and never under .loop/). Mutually exclusive with
                --expect-chain-ancestor. An unreadable or non-conformant anchor is
                a typed issue in the report with ok=false, never a skip.
  --compare FILE|-
                (verdict) compare an attested loop-engineer/verdict@1 predicate
                against this workspace's projection and print an agreement report:
                exit 0 agree, 1 disagree, 2 refusal. Accepts a BARE predicate only —
                an in-toto Statement or a `gh --format json` envelope is refused with
                the jq path to unwrap. This never verifies a signature: authenticity
                is `gh attestation verify`'s job, it runs first, and neither check
                implies the other (signature_checked is always false).
  --emit-subject
                (verdict) write the attested subject's bytes to stdout: exactly the
                64-character lowercase hex chain head, no trailing newline. One
                definition of the byte form, so the signer side and the consumer
                side cannot disagree.
  --executor ID           (run) record this identity as produced_by.executor on the
                          run's evidence records; unset records "unattributed".
  --verifier-identity ID  (run) record this identity as verified_by.by; unset records
                          "loop.run". Equal to --executor => self_verified_evidence.
  --baseline    (metrics only) write docs/metrics-baseline.json over a gate-backed
                run; exits non-zero and writes nothing otherwise.
  -h, --help    Show this help and exit.
  --version     Show the version and exit.
"""


def _version() -> str:
    """Return the package version. Single source of truth is pyproject.toml.

    Prefer installed metadata (which is itself generated from pyproject); fall
    back to reading pyproject.toml at the repo root so `--version` still works
    from an uninstalled/editable checkout.
    """
    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version("loop-engineer")
        except PackageNotFoundError:
            pass
    except Exception:  # pragma: no cover - importlib.metadata ships on 3.10+
        pass
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:  # pragma: no cover - repo layout guarantees this file
        return "unknown"
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
    return match.group(1) if match else "unknown"


def _print_json(report: dict) -> int:
    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") else 1


def _extract_mode_flag(argv: list[str]) -> tuple[str | None, list[str]]:
    """Extract the doctor-family validation mode without changing positional argv."""
    mode: str | None = None
    remaining: list[str] = []
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--mode":
            if index + 1 >= len(argv):
                raise ValueError("--mode requires a value")
            value = argv[index + 1]
            index += 2
        elif arg.startswith("--mode="):
            value = arg.split("=", 1)[1]
            index += 1
        else:
            remaining.append(arg)
            index += 1
            continue
        if value not in VALIDATION_MODES:
            valid = ", ".join(VALIDATION_MODES)
            raise ValueError(f"invalid --mode value {value!r}; expected one of: {valid}")
        mode = value
    return mode, remaining


def _extract_value_flag(argv: list[str], flag: str) -> tuple[str | None, list[str]]:
    value: str | None = None
    remaining: list[str] = []
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == flag:
            if index + 1 >= len(argv):
                raise ValueError(f"{flag} requires a value")
            value = argv[index + 1]
            index += 2
        elif arg.startswith(flag + "="):
            value = arg.split("=", 1)[1]
            index += 1
        else:
            remaining.append(arg)
            index += 1
    return value, remaining


def _read_compare_document(value: str) -> object:
    """Load the attested document from a path or from stdin.

    ONE reader, so the file branch and the '-' branch cannot diverge in their failure
    behavior. Every failure is a VerdictError, so the verdict dispatch renders it as
    `verdict: …` on stderr with exit 2 and no traceback: a bare read_text() here would
    let OSError escape and give the operator Python's own exit 1, which in this CLI
    means "a report said not-ok" — an unreadable file would read as a disagreement.
    """
    from .verdict import VerdictError

    try:
        text = sys.stdin.read() if value == "-" else Path(value).read_text(encoding="utf-8")
    except OSError as exc:                       # missing, a directory, unreadable
        raise VerdictError(f"--compare could not read {value!r}: {exc}") from exc
    except UnicodeDecodeError as exc:            # the #107 lesson
        raise VerdictError(f"--compare input is not valid UTF-8: {exc}") from exc
    if not text.strip():
        # Refused explicitly rather than left to json.loads: an empty stdin is the
        # error a pipeline whose upstream jq produced nothing hits.
        raise VerdictError(f"--compare input is empty: {value!r}")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise VerdictError(f"--compare input is not JSON: {exc}") from exc


def _extract_run_stub_flags(argv: list[str]) -> tuple[list[str], list[str]]:
    """Remove requested but not-yet-supported run-mode flags from argv."""
    flags = {"--continuous", "--approve"}
    present = [arg for arg in argv if arg in flags]
    return present, [arg for arg in argv if arg not in flags]


def _run_metrics(argv: list[str]) -> int:
    """`metrics [--baseline] <target>` — parses its own flag, then delegates to
    scripts/metrics.py (resolved bundle-first, repo-relative fallback)."""
    unknown = [a for a in argv if a.startswith("-") and a != "--baseline"]
    if unknown:
        print(f"metrics: unknown option: {unknown[0]}", file=sys.stderr)
        print(_USAGE, file=sys.stderr)
        return 2
    positional = [a for a in argv if not a.startswith("-")]
    if not positional:
        print("metrics: missing target argument", file=sys.stderr)
        print(_USAGE, file=sys.stderr)
        return 2
    target = Path(positional[0])
    if not target.exists():
        print(
            f"metrics: target path does not exist: {target}\n"
            f"       pass an existing loop workspace or its .loop/ directory.",
            file=sys.stderr,
        )
        return 2
    from ._resources import tools_dir

    scripts_dir = tools_dir()
    sys.path.insert(0, str(scripts_dir))
    import metrics  # type: ignore

    return metrics.run(argv)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv:
        print(_USAGE, file=sys.stderr)
        return 2
    if argv[0] in {"-h", "--help"}:
        print(_HELP)
        return 0
    if argv[0] == "--version":
        print(_version())
        return 0

    command = argv.pop(0)
    if command not in _COMMANDS:
        print(f"unknown loop command: {command}", file=sys.stderr)
        print(_USAGE, file=sys.stderr)
        return 2

    if command == "architect":
        from .architect import ArchitectNotImplementedError, architect_run

        try:
            architect_run()
        except ArchitectNotImplementedError as exc:
            print(f"architect: {exc}", file=sys.stderr)
            return 2
        raise AssertionError(
            "architect_run() returned without raising ArchitectNotImplementedError; "
            "every architect code path must fail loud, never silently succeed"
        )

    if command == "run":
        stub_flags, argv = _extract_run_stub_flags(argv)
        if stub_flags:
            from .runner import RunModeNotImplementedError

            print(f"run: {RunModeNotImplementedError(f'run mode {stub_flags[0]!r} is not implemented')}", file=sys.stderr)
            return 2

    mode = None
    if command in {"doctor", "validate", "verify", "verdict", "plan-lint", "status", "replay", "simulate", "run", "approve", "pause", "resume", "cancel"}:
        try:
            mode, argv = _extract_mode_flag(argv)
        except ValueError as exc:
            print(f"{command}: {exc}", file=sys.stderr)
            print(_USAGE, file=sys.stderr)
            return 2

    expect_chain_head = None
    if command in {"doctor", "validate", "verify"}:
        try:
            expect_chain_head, argv = _extract_value_flag(argv, "--expect-chain-head")
        except ValueError as exc:
            print(f"{command}: {exc}", file=sys.stderr)
            print(_USAGE, file=sys.stderr)
            return 2
        if expect_chain_head is not None and re.fullmatch(r"[0-9a-f]{64}", expect_chain_head) is None:
            print(f"{command}: --expect-chain-head must be a 64-character lowercase hex sha256",
                  file=sys.stderr)
            return 2
    elif any(a == "--expect-chain-head" or a.startswith("--expect-chain-head=") for a in argv):
        # No generic unknown-flag guard exists for the other commands, and scaffold
        # would otherwise CREATE a directory named after the flag.
        print(f"{command}: --expect-chain-head is only valid for doctor/validate/verify",
              file=sys.stderr)
        print(_USAGE, file=sys.stderr)
        return 2

    expect_chain_ancestor = anchor = None
    if command in {"doctor", "validate", "verify"}:
        try:
            expect_chain_ancestor, argv = _extract_value_flag(argv, "--expect-chain-ancestor")
            anchor, argv = _extract_value_flag(argv, "--anchor")
        except ValueError as exc:
            print(f"{command}: {exc}", file=sys.stderr)
            print(_USAGE, file=sys.stderr)
            return 2
        if (expect_chain_ancestor is not None
                and re.fullmatch(r"[0-9a-f]{64}", expect_chain_ancestor) is None):
            print(f"{command}: --expect-chain-ancestor must be a 64-character lowercase hex sha256",
                  file=sys.stderr)
            return 2
        if anchor is not None and expect_chain_ancestor is not None:
            # Silent precedence between an explicit digest and a resolved one is how a
            # gate becomes a suggestion. The action layer, where the inputs are the
            # surface, is where ADR 0002 decision 5's precedence is honored.
            print(f"{command}: --anchor and --expect-chain-ancestor are mutually exclusive",
                  file=sys.stderr)
            print(_USAGE, file=sys.stderr)
            return 2
    else:
        # Same reason as the --expect-chain-head guard above.
        for flag in ("--expect-chain-ancestor", "--anchor"):
            if any(a == flag or a.startswith(f"{flag}=") for a in argv):
                print(f"{command}: {flag} is only valid for doctor/validate/verify",
                      file=sys.stderr)
                print(_USAGE, file=sys.stderr)
                return 2

    compare_path = None
    emit_subject = False
    if command == "verdict":
        try:
            compare_path, argv = _extract_value_flag(argv, "--compare")
        except ValueError as exc:
            print(f"{command}: {exc}", file=sys.stderr)
            print(_USAGE, file=sys.stderr)
            return 2
        if "--emit-subject" in argv:
            emit_subject = True
            argv = [a for a in argv if a != "--emit-subject"]
        if compare_path is not None and emit_subject:
            print("verdict: --compare and --emit-subject are mutually exclusive",
                  file=sys.stderr)
            print(_USAGE, file=sys.stderr)
            return 2
        for flag in ("--verify-signature", "--signature", "--signer-workflow", "--signer-digest"):
            if any(a == flag or a.startswith(f"{flag}=") for a in argv):
                # D10.1: there is no flag to flip. Authenticity is `gh attestation
                # verify`'s job and it runs first; this command establishes agreement.
                print(f"verdict: {flag} is not a verdict option — verdict never verifies a "
                      "signature", file=sys.stderr)
                print(_USAGE, file=sys.stderr)
                return 2
    else:
        # Same reason as the --expect-chain-head guard above: there is no generic
        # unknown-flag guard, so scaffold would CREATE a directory named after the flag.
        for flag in ("--compare", "--emit-subject"):
            if any(a == flag or a.startswith(f"{flag}=") for a in argv):
                print(f"{command}: {flag} is only valid for verdict", file=sys.stderr)
                print(_USAGE, file=sys.stderr)
                return 2

    executor = verifier_identity = None
    if command == "run":
        for flag, slot in (("--executor", "executor"), ("--verifier-identity", "verifier_identity")):
            try:
                value, argv = _extract_value_flag(argv, flag)
            except ValueError as exc:
                print(f"{command}: {exc}", file=sys.stderr)
                return 2
            if value is not None and not value.strip():
                print(f"{command}: {flag} must be a non-empty identity", file=sys.stderr)
                return 2
            if slot == "executor":
                executor = value
            else:
                verifier_identity = value
    else:
        # Same reason as the --expect-chain-head guard above: there is no generic
        # unknown-flag guard, so scaffold would CREATE a directory named after the flag.
        for flag in ("--executor", "--verifier-identity"):
            if any(a == flag or a.startswith(f"{flag}=") for a in argv):
                print(f"{command}: {flag} is only valid for run", file=sys.stderr)
                return 2

    decision = resume_target = reason = note = None
    if command in {"approve", "pause", "resume", "cancel"}:
        try:
            decision, argv = _extract_value_flag(argv, "--decision")
            resume_target, argv = _extract_value_flag(argv, "--resume-target")
            reason, argv = _extract_value_flag(argv, "--reason")
            note, argv = _extract_value_flag(argv, "--note")
        except ValueError as exc:
            print(f"{command}: {exc}", file=sys.stderr)
            print(_USAGE, file=sys.stderr)
            return 2
        if command == "approve" and decision is None:
            print("approve: --decision is required", file=sys.stderr)
            print(_USAGE, file=sys.stderr)
            return 2
        if command == "approve" and decision not in {"approved", "denied"}:
            print("approve: invalid --decision value; expected approved or denied", file=sys.stderr)
            print(_USAGE, file=sys.stderr)
            return 2
        if command == "pause" and reason is None:
            print("pause: --reason is required", file=sys.stderr)
            print(_USAGE, file=sys.stderr)
            return 2
        allowed = {
            "approve": {"decision", "resume_target"}, "pause": {"reason"},
            "resume": {"note"}, "cancel": {"reason"},
        }[command]
        supplied = {name for name, value in {
            "decision": decision, "resume_target": resume_target, "reason": reason, "note": note,
        }.items() if value is not None}
        if not supplied <= allowed or any(arg.startswith("-") for arg in argv) or len(argv) != 1:
            print(f"{command}: unknown option or invalid target arguments", file=sys.stderr)
            print(_USAGE, file=sys.stderr)
            return 2

    # metrics carries its own optional --baseline flag, so it parses its own args
    # before the generic single-target guards below.
    if command == "metrics":
        return _run_metrics(argv)

    if not argv:
        print(f"{command}: missing target argument", file=sys.stderr)
        print(_USAGE, file=sys.stderr)
        return 2
    target = Path(argv[0])

    if command in _READ_COMMANDS and not target.exists():
        if command == "plan-lint":
            hint = "pass an existing loop-engineer/plan@1 JSON file"
        else:
            hint = (
                f"pass an existing workspace root or its .loop/ directory "
                f"(run `{_PROG} scaffold {target}` to create a new contract)"
            )
        print(f"{command}: target path does not exist: {target}\n       {hint}.", file=sys.stderr)
        return 2

    if command == "scaffold":
        from .scaffold import scaffold

        try:
            report = scaffold(target)
        except FileExistsError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(json.dumps(report, indent=2))
        return 0

    if command in {"doctor", "validate", "verify"}:
        resolved_ancestor = expect_chain_ancestor
        anchor_issue = None
        if anchor is not None:
            from .anchor import AnchorError, read_anchor

            try:
                resolved_ancestor = read_anchor(anchor)["chain_head"]
            except AnchorError as exc:
                # A report, never a bare stderr line: the operator's CI reads the JSON,
                # and a stderr line loses the code. resolved_ancestor stays None so the
                # ancestry gate is not ALSO asked a question it has no digest for —
                # one failure, one code.
                resolved_ancestor = None
                anchor_issue = ContractIssue(exc.code, str(exc), Path(anchor))
        try:
            report = doctor_report(target, mode=mode, expect_chain_head=expect_chain_head,
                                   expect_chain_ancestor=resolved_ancestor)
        except ValidationModeError as exc:
            print(f"{command}: {exc}", file=sys.stderr)
            return 2
        if anchor_issue is not None:
            report = {**report, "issues": [*report["issues"], anchor_issue], "ok": False}
        return _print_json(report)

    if command == "verdict":
        from .verdict import VerdictError, build_verdict, compare_verdict, subject_bytes
        from .chain import ChainHashError, canonical_json

        try:
            if emit_subject:
                # buffer.write, never print: a trailing newline would change the subject
                # digest, and the 64-byte form is normative.
                sys.stdout.buffer.write(
                    subject_bytes(build_verdict(target, mode=mode)["chain"]["head"]))
                return 0
            if compare_path is not None:
                return _print_json(compare_verdict(
                    _read_compare_document(compare_path), target, mode=mode))
            print(canonical_json(build_verdict(target, mode=mode)))
            return 0
        except (VerdictError, ChainHashError) as exc:
            print(f"verdict: {exc}", file=sys.stderr)
            return 2

    if command == "plan-lint":
        try:
            return _print_json(validate_plan(target, mode=mode))
        except ValidationModeError as exc:
            print(f"{command}: {exc}", file=sys.stderr)
            return 2

    if command == "migrate":
        from .migrate import migrate_store
        try:
            return _print_json(migrate_store(target))
        except RuntimeStoreError as exc:
            print(f"migrate: {exc}", file=sys.stderr)
            return 2

    if command in {"status", "replay", "simulate"}:
        from .runner import RunnerError
        try:
            if command == "status":
                report = status_report(target, mode=mode)
            elif command == "replay":
                report = replay_report(target, mode=mode)
            else:
                from .simulate import simulate_run

                report = simulate_run(target, mode=mode)
            return _print_json(report)
        except (ValidationModeError, RuntimeStoreError, RunnerError) as exc:
            print(f"{command}: {exc}", file=sys.stderr)
            return 2

    if command == "run":
        from .runner import RunnerError, dispatch_once

        try:
            return _print_json(dispatch_once(target, mode=mode, executor=executor,
                                             verifier_identity=verifier_identity))
        except (RunnerError, RuntimeStoreError, ValidationModeError) as exc:
            print(f"run: {exc}", file=sys.stderr)
            return 2

    if command in {"approve", "pause", "resume", "cancel"}:
        from .runcontrol import approve_run, cancel_run, pause_run, resume_run
        try:
            if command == "approve":
                report = approve_run(target, decision=decision, resume_target=resume_target, mode=mode)
            elif command == "pause":
                report = pause_run(target, reason=reason, mode=mode)
            elif command == "resume":
                report = resume_run(target, note=note, mode=mode)
            else:
                report = cancel_run(target, reason=reason, mode=mode)
            return _print_json(report)
        except (RunControlError, RuntimeStoreError) as exc:
            print(f"{command}: {exc}", file=sys.stderr)
            return 2

    # command == "inspect": keep the historical inspector script as the scoring
    # UI over the same contract artifacts; import lazily to avoid making
    # scripts/ a package.
    from ._resources import tools_dir

    scripts_dir = tools_dir()
    sys.path.insert(0, str(scripts_dir))
    import inspect_loop  # type: ignore

    report = inspect_loop.inspect_loop(str(target))
    print(json.dumps(report, indent=2))
    return 0 if report.get("verdict") != "weak" else 1


if __name__ == "__main__":
    sys.exit(main())
