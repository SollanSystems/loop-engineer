<!-- title: Trigger-phrase disambiguation batch (3 LOW fixes) -->
<!-- labels: good first issue -->

# Trigger-phrase disambiguation batch (3 LOW fixes)

Three small `SKILL.md` frontmatter edits that sharpen router resolution. Each is
independently checkable and none changes behavior — only the trigger prose.

## Problem

Three trigger-phrase weaknesses, all present at this commit:

- **Shared bare "grade" verb.** `skills/loop-evals/SKILL.md` anchors *"or grade a
  long-running agentic run"* and `skills/loop-inspector/SKILL.md` anchors *"grade a
  superpowers / ruflo / .loop harness"* — both hang the same verb on different
  objects, so a bare "grade this" query has no clean winner.
- **`loop-evals` verbosity outlier.** Its `description` scalar runs well past the
  sibling band (~736 chars vs a ~400–510-char peer range), because capability prose
  (the 7-layer suite, deterministic-then-rubric, the regression harness) lives in the
  frontmatter instead of the body.
- **`loop-run` weak first example.** `skills/loop-run/SKILL.md` opens its example
  list with bare `'run the loop'` — the only one of its examples lacking a
  qualifier.

## Proposal

- Make the noun part of each "grade" phrase: evals → *"grade a run's outcome against
  its SPEC"*; inspector → *"grade this harness/contract's readiness"*.
- Trim `loop-evals`' `description` into the ~400–510-char sibling band by moving the
  capability-summary prose into the skill body, leaving trigger phrases + a one-line
  hook in frontmatter.
- Qualify `loop-run`'s opening example: *"run the agent loop"* (or *"run this loop's
  state machine"*).

Keep every `description` a *quoted* YAML scalar (the suite quotes all of them).

## The gate that proves the fix

```bash
python3 scripts/validate_frontmatter.py   # green
python3 scripts/self_eval.py              # green
```

`loop-evals`' frontmatter length should land back in the sibling band; the two
gates above are the whole review bar.
