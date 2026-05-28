# TRADEOFFS

Three things we deliberately did not build, and why.

---

## 1. Authentication and Role-Based Access Control

**What we skipped:** User login, JWT/session auth, and role separation (e.g., data-uploader vs. analyst vs. auditor-viewer).

**Why it matters in production:** An ESG platform handling client data absolutely needs auth. An analyst should not be able to approve their own uploads. An auditor-viewer should have read-only access. Uploaders should not be able to see other clients' data.

**Why we skipped it:** The `ReviewStatus` model has a `reviewed_by` FK to Django's `User` model and `AuditEntry` has an `actor` FK — the data model is wired for auth. What's missing is the middleware: login views, token issuance, and permission checks on each view. Building this correctly for a multi-tenant system (ensuring a user from Tenant A cannot access Tenant B's endpoints) requires either `django-guardian` for object-level permissions or a tenant-aware middleware layer.

In 4 days, building auth correctly would have consumed time better spent on the data model and parsers. A broken auth implementation is worse than no auth — it creates false confidence. We left the hooks in the model and skipped the implementation.

**What we'd do next:** Add `djangorestframework-simplejwt`, a `TenantMembership` model linking Users to Tenants with roles, and a mixin that injects tenant filtering on every view.

---

## 2. Automated Anomaly Detection Beyond Threshold Flags

**What we skipped:** Statistical outlier detection — e.g., flagging records that deviate more than 2 standard deviations from the rolling mean for that meter or plant.

**Why it matters in production:** Our current flagging uses hardcoded thresholds (>50,000 liters, >500,000 kWh). These catch obvious errors but miss contextual ones. A 92,000-liter diesel delivery in a single day (which appears in our sample data) should be flagged not just because it exceeds 50,000 but because it is 13× higher than the same plant's next-largest delivery. Threshold flags would miss this if the threshold were set at 100,000.

**Why we skipped it:** Statistical outlier detection requires historical data. On the first ingestion for a new client, there is no baseline. Building a meaningful anomaly detector requires: (a) enough historical records to compute rolling statistics, (b) a background job (Celery) to re-score records as more data arrives, and (c) per-source thresholds rather than global ones. This is a week of work on its own.

**What we'd do next:** After 3+ ingestion jobs per source, compute per-meter/per-plant mean and standard deviation. Flag records beyond 2σ. Run as a Celery periodic task so existing records get re-evaluated as the baseline grows.

---

## 3. Re-ingestion and Record Versioning

**What we skipped:** The ability to re-upload a corrected file and have it update existing records rather than create duplicates.

**Why it matters in production:** A client submits their Q1 SAP export, an analyst rejects 3 rows because the quantities look wrong, the client re-exports with corrections and re-uploads. Currently, this creates a second `IngestionJob` with new `EmissionRecord` rows. The rejected rows from the first job remain in the database alongside the new correct rows. There is no deduplication.

**Why we skipped it:** Deduplication requires a stable natural key per record — something that identifies "this row represents the same real-world activity as that row." For SAP, that would be `(plant_code, material_number, posting_date, vendor_id)`. For utility, `(meter_id, bill_start_date, bill_end_date)`. For travel, it is harder — Concur has no stable expense ID in a CSV export. Defining these natural keys and building an upsert flow (check for existing record by natural key, update if present, insert if new, handle conflicts) adds significant complexity and requires client confirmation of what constitutes a duplicate.

**What we'd do next:** Add a `source_key` field to `EmissionRecord` — a deterministic hash of the natural key fields per source type. On ingestion, attempt an upsert by `source_key`. If the record exists and is not locked, update it and write an `AuditEntry`. If it is locked (approved), refuse the update and surface the conflict to the analyst.
