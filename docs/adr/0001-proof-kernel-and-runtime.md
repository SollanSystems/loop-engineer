# ADR 0001: Separate the proof kernel from the execution runtime

- **Status:** Accepted
- **Date:** 2026-07-12
- **Decision owners:** Loop Engineer maintainers

## Context

Loop Engineer began as a portable contract and proof layer. Its current core is
valuable because it defines typed terminal states, evidence-gated completion,
anti-cheat checks, bounded repair, and repo-native state without binding those
concepts to a particular orchestration framework.

The product goal is broader: a user should be able to provide a complex goal,
receive a reviewable loop design, execute it through interchangeable agents and
tools, pause for approvals, recover from failure, and obtain an independently
verified terminal result.

Keeping execution out of the project would preserve a small scope, but it would
also leave the most important invariants as instructions that a host agent may
ignore. Folding every concern into one package would create the opposite
problem: provider-specific execution details would contaminate the portable
proof protocol.

## Decision

Loop Engineer will have two first-party layers with a strict dependency
direction.

### 1. Proof kernel

The proof kernel is the stable, runtime-neutral protocol. It owns:

- contract and schema versions;
- deterministic completion-policy evaluation;
- legal state and terminal-state projection;
- evidence and provenance rules;
- verifier and anti-cheat interfaces;
- policy validation and conformance tests;
- event reduction and replay semantics.

The kernel must not import model providers, agent frameworks, or workflow
engines. It may be embedded by foreign runtimes.

### 2. Execution runtime

The execution runtime interprets a validated Loop Plan and owns:

- planning and task scheduling;
- worker leases and attempt numbers;
- agent and tool dispatch;
- budgets, retries, timeouts, pause, resume, and cancellation;
- approvals and side-effect policy;
- checkpointing and crash recovery;
- persistence of immutable events and artifacts.

The runtime depends on the kernel. The kernel never depends on the runtime.

## Governing rule

**Agents propose; the kernel disposes.**

An agent may propose a command, patch, transition, or completion claim. Only the
kernel may validate and commit a state transition or terminal result.

## Immediate consequences

1. `Succeeded` uses an explicit completion policy. The first supported policy is
   `all_required`; every declared criterion must be proven true.
2. Terminal records are immutable. Corrections will be represented by separate,
   auditable administrative events rather than file replacement.
3. New state writers use canonical integer iteration identifiers. Legacy
   numeric strings remain a read-compatibility concern until a versioned state
   migration removes them.
4. The next persistence milestone will introduce an `EventStore` protocol and a
   SQLite/WAL implementation. JSON and Markdown files become projections rather
   than the sole authoritative state.
5. Provider and model selection will be capability-based, not encoded in the
   portable contract as vendor model names.

## Non-goals of this decision

This ADR does not select a distributed scheduler, hosted control plane, web UI,
or model provider. It also does not make structural evidence equivalent to
cryptographic attestation. Those require separate decisions.

## Rejected alternatives

### Remain contract-only

Rejected because the desired product must execute and govern loops end to end.
A prose-only state machine cannot reliably enforce concurrency, approvals,
budgets, or immutable terminal decisions.

### Build a monolithic provider-specific agent framework

Rejected because it would erase the strongest differentiation: a portable proof
contract that can sit above multiple runtimes.

### Permit terminal overwrite for operator convenience

Rejected because an overwritten terminal record destroys audit history and
creates a race in which a later writer can launder an earlier result. A future
supersession event can preserve both the original decision and the correction.
