# Contributing to Loop Engineer

Thanks for your interest. Loop Engineer is a Claude Code plugin plus a portable
loop-contract core. This guide covers how to make a change that passes the gates.

## Ground rule: gates are the bar, not prose

Release readiness is enforced by deterministic gates, not by review opinion. Before
you open a PR, all of these must be green (CI runs them on every push):

```bash
# from the repo root
python3 scripts/validate_frontmatter.py     # SKILL.md frontmatter
python3 scripts/self_eval.py                # 13 structural invariants
python3 -m pytest -q scripts                # the test suite
python3 -m py_compile loop/*.py scripts/*.py
python3 -m loop doctor   examples/coverage-repair   # quickstart still works
python3 -m loop inspect  examples/coverage-repair
```

If you don't have the deps, prefix with `uv run --with pyyaml --with pytest`.

## Repository layout

| Path | What lives here |
|---|---|
| `loop/` | portable contract core + CLI (`python3 -m loop doctor\|validate\|verify\|inspect`) |
| `schemas/` | JSON schemas for contract artifacts (`manifest`, `state`, `tasks`, `terminal`, `receipt`) |
| `skills/` | the 9 Claude Code skills (`<name>/SKILL.md`) |
| `reference/` | deep docs loaded on demand by the skills |
| `templates/` | scaffoldable contract files |
| `scripts/` | the structural gates + runtime-monitor / anti-cheat / benchmark tooling, with tests |
| `examples/` | runnable sample loop contracts |

## Authoring or editing a skill

The `self_eval.py` checks encode hard rules — match them or the gate fails:

- **Frontmatter** must have `name:` and `description:`. The directory name **must equal**
  the frontmatter `name`. Keep the `description` a *quoted* YAML scalar (the suite quotes
  all of them) — an unquoted scalar containing `: ` (colon-space) is parsed as a nested
  mapping and skill discovery breaks. Validate with `python3 scripts/validate_frontmatter.py`.
- **Cross-links.** Every `[[wikilink]]` must resolve to one of the 9 skills (or the known
  external sibling `launch-local-agent`).
- **Reference files.** Every file in `reference/` must be cited by at least one `SKILL.md`.
- **Dispatch routing.** Any fenced code block that dispatches an agent (`agent(` /
  `subagent_type`) must name an explicit `model:` — read→`haiku`, reason→`sonnet`,
  write→`opus`. This keeps cost bounded and dispatches auditable.
- **Bring-your-own-verifier (BYO) default.** This is an open-source plugin: no skill may
  *depend* on an unbundled tool. If a skill mentions an optional integration
  (`/verify-slice`, `.gsd/` receipts, the routing hooks), it must **also** name the
  bundled default path (`scripts/verify-fast`→`verify-full`, the `loop` CLI, or
  `.loop/receipts`). External tools appear only as clearly-labeled optional integrations.
- **No secrets.** No secret-shaped literals anywhere (the `no-secrets` check enforces this).

## Turning a fixed bug into a permanent test

In the spirit of the suite's own flywheel: when you fix a real defect, add a regression
test (under `scripts/test_*.py`) or an eval case so the same failure can't silently return.

## Commit & PR conventions

- Conventional commits: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`, `ci:`.
- One logical change per PR; keep the diff reviewable.
- Update `CHANGELOG.md` under `## Unreleased` for any user-visible change.
- Confirm the gates above are green locally before requesting review.

## Reporting bugs / proposing features

Open an issue using the templates in `.github/ISSUE_TEMPLATE/`. For security issues, see
[SECURITY.md](SECURITY.md) — do **not** open a public issue.
