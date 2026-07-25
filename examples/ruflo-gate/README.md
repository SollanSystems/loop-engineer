# ruflo recipe — swarm below, acceptance gate above

A runnable **host-side supervisor** around [ruflo](https://github.com/ruvnet/ruflo)'s
blocking swarm CLI. ruflo keeps its own orchestration substrate (Queen coordinator,
worker agents, SPARC phases, `.swarm/` + `.hive-mind/` state); Loop Engineer adds
the contract/proof tier above it — evidence-backed state the `loop` CLI can
independently validate and score.

## Why a supervisor and not a hook

`ruflo hive-mind spawn "<objective>" --claude` spawns the Claude Code CLI as the
swarm's body, **blocks** until that child exits, and maps `exit 0` to success.
There is no swarm-terminal callback to register: the `hooks` subcommands are calls
*into* ruflo, and the plugin `HookEvent` enum has no swarm-level terminal event
(`swarm:consensus-reached` appears in ruflo's docs but not in its implementation).
So the gate lives in the process that launches the CLI — plus, optionally, a
second independent gate inside the child via this repo's Claude Code `Stop`-hook
firewall (`hooks/stop_firewall.py`).

## What it shows

`swarm_example.py` supervises one run:

1. **drive** the swarm (replayed by default — see below),
2. **observe** only host-side surfaces: `.swarm/state.json`, `.swarm/tasks/*.json`,
   `.swarm/agents/*.json`, `.swarm/coordination/*.json`, and the
   `ruflo memory export` JSON,
3. **gate** it with the withheld holdout split (`holdout_gate.decide`) plus the
   trajectory sweep (`anticheat_scan.scan`) over the agent trails,
4. **project** through `to_terminal_state` and **record** via `loop.emit`, which
   refuses a dishonest `Succeeded` before anything hits disk.

The swarm's own `sparc-phases` `acceptanceCriteria` supply the criteria
*vocabulary* (`AC-1`…`AC-3`); their truth comes from the withheld checks. The
swarm's `sparc-gates` self-verdict (all phases `pass`, `truthScore: 0.97`) is
recorded as an observation in `swarm-observation.json` and never used to decide.

## Fixture replay is the default — and it is stated, not hidden

A live ruflo run needs Node, `npx ruflo`, the `claude` binary, credentials and
real model spend, so the shipped default **replays the committed recording in
`fixture/`** — a `.swarm/` tree in ruflo's layout plus the work product the
recorded run left behind. `--live` opts into the real invocation.

Only the swarm is recorded. The gate, the projection, `loop.emit`, `loop doctor`
and `loop metrics` all execute for real against the replayed workspace. A recipe
that quietly faked the engine *and* the gate would be exactly the false
completion this project exists to catch.

## Run it

```bash
pip install loop-engineer
python swarm_example.py demo-run/          # replay: Succeeded, offline
loop doctor demo-run/                      # -> {"ok": true, ...}
loop metrics demo-run/                     # -> clean scorecard (FCR 0.0)
```

### Demos

| Flag | What it proves |
|---|---|
| `--sabotage-holdout` | the work product still claims 41 unique rows (visible green) but the dropped-row log is truncated (holdout red) → `FailedUnverifiable`, `false_completion: true`, **never** `Succeeded` |
| `--simulate-interrupt` | ruflo exits **0** on Ctrl-C, and the gate is green — yet the supervisor's own interrupt flag yields `AbortedByHuman` |
| `--declare-unmapped-criterion` | the swarm declares `AC-4` that no check covers → `FailedSpecGap`, the failure a self-reporting coordinator hides |
| `--live` | really runs `npx ruflo@3.32.9 hive-mind spawn … --claude` (Node + `claude` + credentials + spend) |

In live mode the supervisor installs a `SIGINT` handler *before* spawning, because
ruflo's own SIGINT path calls `process.exit(0)` — `human_abort` is never inferred
from the exit code.

The gate tools (`holdout_gate`, `anticheat_scan`) resolve from `loop._resources`,
so a plain `pip install` is enough; a repo checkout picks them up from `scripts/`.

## The general pattern

The complement framing, the full host-side signal table, the three traps, and the
copy-paste (zero-install) projection live in
[`docs/integrations/ruflo.md`](../../docs/integrations/ruflo.md).

Verified against `ruflo` 3.32.9 (2026-07-25). Fixture prose is original; only
directory names and JSON key names follow ruflo's conventions.
