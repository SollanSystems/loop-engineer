# Product Mission

> Fictional sample content for the vendored fixture. Not a real project.

## Problem

Small teams import contacts from spreadsheet exports that overlap. The same
person appears in two files with different casing, so the importer writes the
same contact twice and the address book fills with near-duplicates that are
tedious to reconcile by hand.

## Target Users

Operators and sales assistants who bulk-load contact lists into a lightweight
CRM and expect the import to be safe to run more than once without doubling
their records.

## Solution

Every import normalizes and de-duplicates before it writes. A contact is keyed
on its lowercased email and phone, the first occurrence wins, and later
collisions are dropped and logged. Re-running the same source is a no-op, so
imports become idempotent instead of destructive.
