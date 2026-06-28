# Security Policy

## Supported versions

Loop Engineer is distributed as source. Security fixes land on the latest release
and on `main`. Pin a tag if you need a stable point.

## Reporting a vulnerability

**Do not open a public issue for a security problem.**

Use GitHub's private vulnerability reporting:
**Security → Report a vulnerability** on the repository
(<https://github.com/SollanSystems/loop-engineer/security/advisories/new>).

Please include reproduction steps and the affected file(s)/skill(s). You'll get an
acknowledgement, and a fix or mitigation plan once the report is triaged.

## Scope notes for this project

Loop Engineer designs and operates *autonomous agent loops*, so a few of its own
guarantees are security-relevant — issues in these areas are in scope:

- **Verifier-gaming defenses.** The anti-cheat scanner (`scripts/anticheat_scan.py`)
  and held-out gate (`scripts/holdout_gate.py`) exist to catch a loop editing its own
  tests/fixtures/spec to manufacture a pass. A bypass of these is a security issue.
- **Approval boundary.** The contract pauses at side-effect boundaries (destructive
  commands, secrets, production mutation, money movement). A path that lets a loop cross
  one without the approval gate is in scope.
- **Plan-then-execute / prompt injection.** The skills instruct loops to treat untrusted
  content (web, scraped docs, tool output) as data, never as instructions. A documented
  pattern that violates this is in scope.

Out of scope: vulnerabilities in *your* loop's task code, in optional third-party
integrations, or in Claude Code itself (report those upstream).

## Handling of secrets

This repository must contain no secrets. The `no-secrets` structural check
(`scripts/self_eval.py`) scans for secret-shaped literals on every run; if you find one
that slipped through, report it via the private channel above.
