---
issue: 1235
title: Normalization key
analyzed: 2026-07-09T13:40:55Z
estimated_hours: 4
parallelization_factor: 1.6
---

# Parallel Work Analysis: Issue #1235

## Overview

The normalization-key task splits cleanly into the helper itself and its test
suite, which live in different files and can be built by two agents at once
once the function signature is agreed.

## Parallel Streams

### Stream A: Key helper
**Scope**: Implement `normalize_key(email, phone)` and wire its import path.
**Files**: `import_contacts.py`
**Can Start**: immediately
**Estimated Hours**: 3
**Dependencies**: none

### Stream B: Key unit tests
**Scope**: Cover mixed-case, whitespace, and empty-phone fixtures for the key.
**Files**: `tests/test_normalize_key.py`
**Can Start**: after Stream A publishes the signature
**Dependencies**: Stream A

## Coordination Points
### Shared Files
None — the two streams touch disjoint files.
### Sequential Requirements
Stream B imports the helper, so it lands after Stream A's signature is stable.

## Conflict Risk Assessment

Low. The only shared surface is the function signature, which is fixed in the
task description before either stream starts.

## Parallelization Strategy

Publish the signature first, then run both streams; the test agent stubs
against the agreed signature until the helper lands.

## Expected Timeline
- With parallel execution: 3h wall time
- Without: 4h
- Efficiency gain: 25%
