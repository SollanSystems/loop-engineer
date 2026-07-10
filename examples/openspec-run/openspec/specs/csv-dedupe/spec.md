# csv-dedupe Specification

## Purpose
Define how the contact importer collapses duplicate rows that arrive from
overlapping export files so that each real person is stored once, the earliest
occurrence is the record that survives, and re-running the import changes
nothing. This is the living record synced from the 2026-07-09 dedupe-csv-rows
change.

## Requirements

### Requirement: Collapse contacts on a case-folded identity key
The importer SHALL treat two rows as the same contact when their email and
phone match after lowercasing and trimming surrounding whitespace.

#### Scenario: Same contact, different casing
- **WHEN** two source rows carry `Ada@Site.io` and `ada@site.io` with the same phone
- **THEN** the importer stores a single contact
- **AND** the row read first is the one retained

#### Scenario: Distinct contacts are preserved
- **WHEN** two rows differ in either the folded email or the folded phone
- **THEN** both are stored as separate contacts

### Requirement: Import is idempotent across repeated runs
The importer SHALL insert no additional rows when the same sources are imported
a second time.

#### Scenario: Second run over unchanged inputs
- **WHEN** the two sample files are imported and then imported again
- **THEN** the first run stores 41 unique contacts from 57 raw rows
- **AND** the second run stores 0 new contacts

### Requirement: Dropped duplicates are recorded with provenance
The importer SHALL append every skipped duplicate to `dedupe.log` with the
source file and line number it came from.

#### Scenario: A duplicate is skipped
- **WHEN** a row collides with an already-stored contact
- **THEN** the importer does not insert it
- **AND** it writes one `dedupe.log` line naming the source file and line number
