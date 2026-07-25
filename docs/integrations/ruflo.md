# ruflo — swarm below, acceptance gate above

[ruflo](https://github.com/ruvnet/ruflo) owns the ORCHESTRATE tier: a multi-agent
swarm that spawns a Queen coordinator and worker agents over the Claude Code CLI,
runs the SPARC phases, and keeps its state in `.swarm/` and `.hive-mind/`. What it
cannot do is tell you whether the objective was actually met — a swarm's terminal
is "the coordinator decided", recorded as a child-process exit code plus rows the
swarm wrote about itself. Loop Engineer adds the tier *above* it: one acceptance
gate the swarm as a whole must pass. It never replaces ruflo; it certifies what
the swarm produced.

## The seam: a host-side supervisor, not a swarm hook

`ruflo hive-mind spawn "<objective>" --claude` **blocks** — it spawns the `claude`
binary as the swarm's execution body and awaits its exit, mapping `exit 0` to
success. So the integration point is the process you already control: the
supervisor that launches the CLI and reads the run directory afterwards.

> There is **no swarm-terminal callback to register.** ruflo's `hooks` subcommands
> are calls *into* its learning system (`ruflo hooks post-task …`), and the plugin
> `HookEvent` enum carries no swarm-level terminal event — the `swarm:consensus-reached`
> / `task:post-complete` names in the docs do not exist in the implementation.
> Gate from the outside instead. For a second, independent gate *inside* the
> swarm's child, register [`hooks/stop_firewall.py`](../../hooks/stop_firewall.py)
> as a Claude Code `Stop` hook: it blocks a turn that ends on a `Succeeded` claim
> `loop doctor` disagrees with.

## The pattern

```python
from loop import emit
from loop.integrations import EngineOutcome, to_terminal_state

run = subprocess.run(["npx", "ruflo@3.32.9", "hive-mind", "spawn", objective,
                      "--claude", "--non-interactive"], cwd=ws)   # blocks

obs = observe(ws)                                    # .swarm/ JSON + memory export
gate = holdout_gate.decide(visible, holdout)         # the split the swarm never saw
ac = anticheat_scan.scan(diff_text=git_diff, trajectory=agent_trails(obs))

criteria_met = {cid: proven.get(cid) for cid in declared_criteria(obs["export"])}
terminal = to_terminal_state(
    outcome=EngineOutcome(
        reached_end=run.returncode == 0 and obs["state"]["status"] in {"ready", "initialized", "stopped"},
        human_abort=supervisor_was_interrupted(),    # NEVER inferred from the exit code
        artifacts=[...],
    ),
    gate_verdict=gate, anticheat=ac, criteria_met=criteria_met,
)
emit.terminate(ws, state=terminal["state"], criteria_met=terminal["criteria_met"],
               evidence=terminal["evidence"], false_completion=terminal["false_completion"],
               reason=terminal["reason"], iteration_id=1)
```

`loop/integrations.py` needs **no ruflo-specific code** — every input is host-side
observable, and ruflo itself is unmodified.

## What a supervisor can read (zero ruflo changes)

| Signal | Shape |
|---|---|
| exit code of `hive-mind spawn … --claude` | `0` == the swarm's self-report of success |
| `.swarm/state.json` | `{id, topology, maxAgents, strategy, v3Mode, initializedAt, status}` |
| `.swarm/tasks/*.json` | per-task `status` ∈ `completed｜done｜in_progress｜running｜pending` |
| `.swarm/agents/*.json`, `.swarm/coordination/*.json` | the agent trails and consensus rows |
| `ruflo swarm status --format json` | live counts, progress, metrics |
| `ruflo memory export -o <file>` | the SPARC namespaces, incl. declared `acceptanceCriteria` |
| `ruflo autopilot status --json` | re-engagement loop state (`--max-iterations`, `--timeout`) |

Authoritative run state lives in binary SQLite (`.swarm/memory.db`,
`.hive-mind/hive.db`). Never parse those — `memory export` is the supported
serialization. Note the flag inconsistency: `swarm status --format json` but
`autopilot status --json`.

### Three traps

1. **Ctrl-C exits 0.** ruflo's SIGINT path prints "Pausing session", kills the
   child and calls `process.exit(0)` — an interrupted run is indistinguishable
   from a successful one by exit code. `AbortedByHuman` must come from the
   supervisor's own signal handler; never derive it from ruflo.
2. **`ruflo verify` is install-integrity, not a run verdict.** It checks the
   SHA-256 + Ed25519 witness of the *installed artifact* against
   `verification.md.json`. It says nothing about whether the objective was met —
   wiring it as the gate would certify that the package downloaded correctly.
3. **`sparc-gates` is the swarm grading its own homework.** The memory export's
   `sparc-gates` namespace records per-phase `pass` rows and a `truthScore`. Read
   the `sparc-phases` `acceptanceCriteria` as a criteria *vocabulary*, record the
   self-report as observation — and let the withheld holdout gate decide.

## ruflo signal → typed terminal state

| ruflo signal | Typed terminal state |
|---|---|
| exit 0, swarm settled, holdout green + anticheat clean, every declared criterion proven | `Succeeded` |
| exit 0, visible green / holdout red | `FailedUnverifiable` (`false_completion: true`) |
| the swarm declared an AC no check covers | `FailedSpecGap` |
| autopilot `--max-iterations` / `--timeout` reached without a green gate | `FailedBudget` |
| non-zero exit with no completed tasks (MCP / provider / credential failure) | `FailedBlocked` |
| operator interrupt, recorded by the supervisor | `AbortedByHuman` |
| anticheat CRITICAL (gate tampering) | `FailedSafety` |

Precedence is `to_terminal_state`'s fixed order — safety → human → blocked →
budget → spec-gap → gate — so an interrupted or gamed run can never launder
itself into `Succeeded`.

## Zero-install mode

The `loop.integrations` module is convenience, not a requirement — the whole
projection is the SAME ~15 lines as the LangGraph and Temporal recipes (the
adapter is engine-neutral):

```python
def to_terminal(gate, anticheat, criteria_met, evidence,
                *, human_abort=False, blocked=None, over_budget=False):
    fc = gate.get("false_completion") is True
    if anticheat.get("downgrade_to") == "FailedSafety": state = "FailedSafety"
    elif human_abort: state = "AbortedByHuman"
    elif blocked: state = "FailedBlocked"
    elif over_budget: state = "FailedBudget"
    elif any(v is None for v in criteria_met.values()): state = "FailedSpecGap"
    elif (not gate or not anticheat or anticheat.get("downgrade_to")
          or gate.get("verdict") != "Succeeded" or fc
          or not any(criteria_met.values()) or not evidence): state = "FailedUnverifiable"
    else: state = "Succeeded"
    return {"schema": "loop-engineer/terminal@1", "state": state,
            "criteria_met": {k: v is True for k, v in criteria_met.items()},
            "evidence": list(evidence), "false_completion": fc}
```

## Gate it in CI

```yaml
- run: pip install loop-engineer
- run: loop doctor run/          # -> {"ok": true}: the contract is structurally honest
- run: loop metrics run/         # -> false_completion_rate + evidence-backed scorecard
```

`loop metrics` scores the run from its on-disk evidence — not from the swarm's
narration, its consensus rows, or its `truthScore`.

Verified against `ruflo` 3.32.9 (2026-07-25). ruflo moves fast (27 minor versions
in three months), so pin the version you supervise.

Full runnable example (happy path + `--sabotage-holdout` false-completion demo +
interrupt and spec-gap demos, replaying a committed recording so it runs offline):
[`examples/ruflo-gate/`](../../examples/ruflo-gate/).
