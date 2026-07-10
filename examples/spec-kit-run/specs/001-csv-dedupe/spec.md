# Feature Specification: CSV Contact Dedupe

**Feature Branch**: `001-csv-dedupe`

**Created**: 2026-07-09

**Status**: Draft

**Input**: User description: "import_contacts.py writes duplicate rows when the same person appears in two source files with different casing — dedupe on import and keep an auditable log of what was dropped."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Merge two contact exports without duplicates (Priority: P1)

An operator imports two overlapping contact exports where the same person is
written with different capitalization in email and phone fields. They want one
clean contact list, not a pile of near-identical rows, and a record of exactly
which rows were folded away.

**Why this priority**: This is the entire reason the feature exists; without it the
import is worse than useless because it inflates the list with silent duplicates.

**Independent Test**: Run the import against the two sample exports and confirm the
resulting list holds one row per person plus a log naming every dropped row.

**Acceptance Scenarios**:

1. **Given** two exports totaling 57 rows with case-varying duplicates, **When** the
   operator runs the import, **Then** the contact list holds 41 unique rows.
2. **Given** a contact list already produced by a prior import, **When** the operator
   runs the same import again, **Then** zero new rows are added.
3. **Given** a row folded into an earlier one, **When** the import finishes, **Then**
   `dedupe.log` names the dropped row and the source line it came from.

### Edge Cases

- What happens when a row has an email but a blank phone, or the reverse? The
  present fields still form the key; a missing field is treated as empty, not as a
  wildcard that collapses unrelated people together.
- How does the tool handle surrounding whitespace and mixed casing in the same
  field? Both are normalized away before the key is compared.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST derive a dedupe key from the lowercased, trimmed email and
  phone of each row before deciding whether to keep it.
- **FR-002**: System MUST keep the first row seen for a given key and discard every
  later row that resolves to the same key.
- **FR-003**: System MUST append each discarded row to `dedupe.log` together with the
  source file and line number it was read from.
- **FR-004**: System MUST be idempotent — re-importing already-loaded data MUST add
  no new rows.
- **FR-005**: System MUST expose the import as a command-line entry point that reads
  the source files and reports the surviving-row count on completion.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Importing the two sample exports yields exactly 41 unique contacts from
  57 input rows.
- **SC-002**: A second run over the same result adds 0 rows.
- **SC-003**: Every dropped row appears in `dedupe.log` with a resolvable source line
  number, so 100% of removals are auditable by hand.

## Assumptions

- The two source files are the canonical inputs; no third source is in scope for v1.
- Email and phone together are enough to identify a person for this dataset; no
  external identity service is consulted.
- The output list and `dedupe.log` are written to the working directory the command
  is invoked from.
