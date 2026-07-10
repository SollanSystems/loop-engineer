# Contacts Toolkit Constitution

<!--
SYNC IMPACT REPORT
- Version change: none -> 1.0.0
- Principles added: I. Deterministic Output, II. Test-Backed Change
- Templates aligned: plan.md Constitution Check gate references both principles
- Follow-up TODOs: none
-->

## Core Principles

### I. Deterministic Output

Any transformation that reshapes source rows MUST produce the same result for the
same inputs, independent of file order or run count. Re-running an import over
data that is already loaded MUST add nothing new. When a row is discarded, the
tool MUST record which source line it came from, so the outcome can be audited by
hand rather than trusted on faith.

### II. Test-Backed Change

No behavior ships without an automated test that would fail if the behavior
regressed. Deduplication logic in particular MUST be covered by a test that pins
the exact surviving-row count for a known fixture, so a silent drift in the key
strategy is caught before it reaches a user's contact list.

## Governance

This constitution is the authority the plan's Constitution Check gate is measured
against. A plan that conflicts with a MUST here cannot pass the gate until the
conflict is resolved or the constitution is amended with a recorded reason.
Amendments bump the version and note the rationale in the sync impact report above.

**Version**: 1.0.0 | **Ratified**: 2026-07-09 | **Last Amended**: 2026-07-09
