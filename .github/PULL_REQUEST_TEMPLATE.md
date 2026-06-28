<!-- Conventional-commit title, e.g. "fix(loop-run): ..." -->

## What & why

<!-- The change and the problem it solves. Link any issue (Closes #N). -->

## Gates (must be green)

- [ ] `python3 scripts/validate_frontmatter.py`
- [ ] `python3 scripts/self_eval.py` (13/13)
- [ ] `python3 -m pytest -q scripts`
- [ ] `python3 -m py_compile loop/*.py scripts/*.py`
- [ ] `python3 -m loop doctor examples/coverage-repair` still passes

## Checklist

- [ ] If a skill mentions an optional integration, it also names the bundled default path (BYO-default)
- [ ] Any agent-dispatch code fence names an explicit `model:`
- [ ] Added a test/eval case for any fixed bug
- [ ] Updated `CHANGELOG.md` under `## Unreleased`
