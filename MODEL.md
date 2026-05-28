# DATA MODEL

## Overview

The data model is designed around four concerns: multi-tenancy, source-of-truth tracking, unit normalization, and audit trail. Every design decision below maps directly to a real operational constraint in ESG data management.

---

## Entity Map

```
Tenant
  └── DataSource (source_type: sap_flat_file | utility_csv | concur_csv)
        └── IngestionJob (status: pending → processing → done | failed)
              └── EmissionRecord (one row = one activity event)
                    ├── ReviewStatus (one-to-one, pending → approved | rejected)
                    └── AuditEntry (append-only log of every state change)
```

---

## Multi-Tenancy

Every `EmissionRecord`, `DataSource`, and `IngestionJob` is scoped to a `Tenant` via a foreign key. The `Tenant` model uses a `slug` field as the lookup key — it is URL-safe, human-readable, and passed as a query parameter on every API request. This means:

- No row from Tenant A can ever appear in Tenant B's dashboard
- A single Django deployment serves multiple enterprise clients
- Tenant isolation is enforced at the ORM query level, not in application logic

**Why slug over ID?** Slugs are stable identifiers that survive database migrations and can be included in API calls without exposing internal PKs.

---

## Source-of-Truth Tracking

Three layers track provenance for every record:

**1. `DataSource`** — records *what* the source is (SAP flat file, utility portal CSV, Concur export) and which tenant it belongs to. The `config` JSONField stores source-specific metadata (e.g., grid region for utility data, SAP plant lookup table path) without requiring schema changes per client.

**2. `IngestionJob`** — records *when* a file was ingested, which file it was (`filename`), and what happened (`rows_total`, `rows_ok`, `rows_failed`, `error_log`). Every `EmissionRecord` carries a FK to its `IngestionJob`, so an analyst can always answer: "which upload did this row come from?"

**3. `raw_payload` on `EmissionRecord`** — the full original CSV row is stored as JSON, exactly as received, before any transformation. This means:
- The normalized value can be recomputed if the emission factor changes
- An auditor can verify our math against the source file
- Nothing is ever silently discarded

---

## Raw vs. Normalized Split

Each `EmissionRecord` carries both the original value and the normalized result:

| Field | Purpose |
|---|---|
| `raw_activity_value` | The number as it appeared in the source file |
| `raw_unit` | The unit as it appeared (e.g., `L`, `MWh`, `M3`) |
| `raw_payload` | Full source row as JSON |
| `normalized_value` | Value converted to a common unit |
| `normalized_unit` | `liters`, `kwh`, `km`, or `nights` |
| `emission_factor` | The factor applied |
| `emission_factor_source` | Citation (e.g., `DEFRA 2023 — diesel`) |
| `co2e_kg` | Final computed emissions |

**Why keep raw separately?** Emission factors change. DEFRA updates its figures annually. If we only stored `co2e_kg`, we could not recompute or verify. Storing `raw_activity_value + emission_factor + co2e_kg` separately means we can audit the calculation and re-run it with updated factors.

---

## Scope 1 / 2 / 3 Categorization

| Source | Scope | Category |
|---|---|---|
| SAP — fuel (diesel, petrol, LNG) | 1 | `fuel_combustion` |
| SAP — unknown/non-fuel materials | 3 | `purchased_goods` |
| Utility electricity | 2 | `electricity` |
| Concur — flights | 3 | `business_travel_air` |
| Concur — hotels | 3 | `business_travel_hotel` |
| Concur — taxi, car rental, train | 3 | `business_travel_ground` |

Scope is assigned at parse time by the parser, based on material description (SAP), commodity type (utility), or expense type (Concur). It is stored as a `CharField` with choices `1`, `2`, `3` — not an integer — to avoid accidental arithmetic on scope values.

---

## Audit Trail

The `AuditEntry` model is append-only. Every time a record's review status changes, a new row is inserted with:

- `record` — which emission record changed
- `actor` — which user made the change (nullable for system actions)
- `action` — e.g., `review_approved`, `review_rejected`
- `before` — JSON snapshot of state before the change
- `after` — JSON snapshot of state after the change
- `ts` — timestamp (auto)

This satisfies GHG Protocol audit requirements: a verifier can reconstruct the complete history of any record without relying on application logs.

---

## Review and Lock Lifecycle

```
EmissionRecord created → ReviewStatus: pending
Analyst approves → ReviewStatus: approved + EmissionRecord.is_locked = True
Analyst rejects → ReviewStatus: rejected (not locked, can be re-ingested)
```

Once a record is locked (`is_locked = True`), the `ReviewView` refuses further changes. This is the gate before data goes to external auditors. Locked records cannot be modified even by re-upload — they require a new ingestion job that produces a new record.

---

## Flagging

Records are flagged at parse time when the parser detects:

- Unrecognized unit or material type
- Statistically anomalous values (>50,000 liters for fuel, >500,000 kWh for electricity)
- Zero or negative usage
- Missing flight distance (unknown airport codes)
- Missing hotel nights defaulted to 1

Flags are stored in `is_flagged` (boolean) and `flag_reason` (text). The analyst dashboard surfaces flagged records prominently so they are reviewed before approval.

---

## What This Model Intentionally Does Not Include

See `TRADEOFFS.md` for three deliberate omissions and their justification.
