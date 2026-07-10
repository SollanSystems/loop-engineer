# ruflo-run — a vendored foreign-harness fixture

A minimal, sanitized run directory in the layout that
[ruflo](https://github.com/ruvnet/ruflo) (ruvnet/ruflo, formerly claude-flow,
v3.5) leaves behind after `npx ruflo init` scaffolds a workspace and a SPARC
swarm drives a feature to done. Layout follows
`ruvnet/ruflo@7ef4d4e655d81c0451f6f40f35729cce6c9928e7`. ruflo is MIT-licensed,
but per this repo's fixture rule only directory names, JSON key names, and
section headings follow its conventions — **every sentence of prose here is
original and fictional**. No template body text is copied.

The recorded run is the same fictional task used across the other fixtures: a
CSV-dedupe change to `src/import_contacts.py` (normalize on
`(lower(email), lower(phone))`, keep the first-seen row, log dropped rows to
`dedupe.log`, 41 unique from 57 input rows, idempotent on re-run), dated
2026-07-09.

## What is (and isn't) vendored

ruflo keeps authoritative run state in **binary SQLite** — `.swarm/memory.db`
(SPARC phase artifacts, gate records, learned patterns) and `.hive-mind/hive.db`
(queen/worker/task rows). Those are not human-readable, so this fixture vendors
the harness's own documented serialization instead: `.swarm/memory-export.json`
is the exact shape produced by `ruflo memory export -o backup.json`, alongside
the JSON metrics and security-gate files that `init` and the hooks write. No
binary database is included.

## Composes, does not compete

ruflo is an orchestration and memory substrate — it spawns a swarm, runs the
five SPARC phases behind quality gates, and records completion across a memory
namespace, a gate row, and a session-end git tag. Loop Engineer is the contract
layer that grades whether that end state is *provable*. The honest score this
fixture earns is not a knock on ruflo: it measures what a DB-backed swarm run
structurally leaves outside a portable contract — no typed terminal record and
no held-out anti-cheat gate an outside reader can replay. See
`docs/gap-reports/` for the item-by-item reading.

## Reproduce

```bash
uv run --with pyyaml python3 -B -m loop inspect examples/ruflo-run || true
```

A weak verdict exits non-zero; the `|| true` keeps that expected result from
failing a shell that chains commands.
