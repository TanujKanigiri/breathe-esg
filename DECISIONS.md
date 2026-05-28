# DECISIONS

Every ambiguity we resolved, what we chose, why, and what we'd ask the PM.

---

## SAP: Which Export Format?

**Ambiguity:** SAP exposes data via IDoc, OData, BAPI, or flat file. Each has different integration complexity.

**Decision:** SAP flat file CSV — specifically the MB51 goods movement report format.

**Why:**
- MB51 is the report SAP sustainability leads actually run manually. It is the most common format we would receive from a client's SAP team in an onboarding scenario.
- IDoc and BAPI require SAP BASIS team involvement and middleware. That is a weeks-long integration, not a 4-day prototype.
- OData is viable for production but requires client SAP configuration and authentication that varies by version (ECC vs S/4HANA).
- Flat file upload is the realistic ingestion mode for an enterprise client sending us data over email or SFTP during onboarding.

**Subset handled:** Goods movement (movement type 101 — goods receipt). We capture: plant code (WERKS), material number (MATNR), material description (MAKTX), quantity (MENGE), unit (MEINS), posting date (BUDAT), vendor (LIFNR), movement type (BWART).

**Ignored:** Cost center allocations, purchase order references, batch numbers, storage location (LGORT), GL account (HKONT). These are relevant for Scope 3 category 1 (purchased goods) calculations but require a material master lookup table that the client would need to provide separately.

**What we'd ask the PM:**
- Does the client run ECC or S/4HANA? This affects available OData services.
- Can they provide a material master extract so we can map MAT codes to fuel types rather than relying on MAKTX descriptions?
- Are goods receipts the right movement types, or do they also want issues (261) for internal consumption?

---

## SAP: Column Name Normalization

**Ambiguity:** SAP exports have German column headers in some configurations (e.g., `BUCHUNGSDATUM` instead of `BUDAT`, `BEZEICHNUNG` instead of `MAKTX`).

**Decision:** We built a `COLUMN_MAP` dictionary that maps both German and English variants to canonical internal names before processing.

**Why:** A single enterprise client may have mixed-language SAP configurations across plants. Rather than requiring the client to pre-process their export, we absorb that complexity in the parser.

---

## SAP: Fuel Type Detection

**Ambiguity:** SAP material descriptions (MAKTX) are free text entered by whoever set up the material master. They are inconsistent.

**Decision:** Fuzzy keyword matching on `material_desc` — check for `diesel`, `hsd`, `petrol`, `gasoline`, `lng`, `cng`, `gas` as substrings.

**What triggers a flag:** If no fuel keyword is matched, the record is flagged with `Could not determine fuel type from: <description>` and `co2e_kg` is left null. The row is still ingested — it is not dropped — because the analyst may know what the material is.

**What we'd ask the PM:** Can the client provide a mapping table of their MATNR codes to fuel type? That would make this deterministic rather than heuristic.

---

## Utility: Which Ingestion Mode?

**Ambiguity:** Utility data can come as a portal CSV export, a PDF bill, or an API (Green Button, utility-specific).

**Decision:** Portal CSV export.

**Why:**
- Green Button API is available from some US utilities but almost no Indian utilities, and the client appears India-based given the travel data.
- PDF parsing is fragile — bill layouts differ per utility, per tariff structure, and change without notice. It is the right long-term answer but not a reliable prototype approach.
- Portal CSV is what a facilities manager actually downloads. It is the most common format we would receive during onboarding. It is structured enough to parse reliably.

**Subset handled:** Account number, meter ID, site name, commodity (electricity only), unit (kWh or MWh), billing period start/end, usage quantity. We ignore demand charges, tariff codes, power factor, reactive power, and fuel adjustment clauses.

**Billing period alignment:** We do not assume billing periods align to calendar months. We use `bill_end_date` as `activity_date`. If an analyst needs monthly allocation, that is a downstream reporting concern, not an ingestion concern.

**What we'd ask the PM:**
- Which grid region should we use for the emission factor? We default to India (0.82 kg CO2e/kWh, CEA 2023) but this must be confirmed per site.
- Do they have multiple sites in different states with different grid mixes?

---

## Utility: Mixed Units (kWh vs MWh)

**Ambiguity:** Sample data shows `MTR-WH-02` reporting in MWh while all other meters use kWh.

**Decision:** We built a `UNIT_TO_KWH` lookup that normalizes all readings to kWh before computing emissions. MWh × 1000 = kWh. The normalized unit stored is always `kwh`.

**Why this matters:** If this conversion were missed, MTR-WH-02's 55.4 MWh would be treated as 55.4 kWh — a 1000× undercount. This is a real-world error that happens in practice.

---

## Utility: Zero-Usage Rows

**Ambiguity:** `MTR-FAC-02` has zero usage, zero demand, zero cost. Keep or drop?

**Decision:** Ingest the row, flag it with `Zero or negative usage`.

**Why:** A zero reading is meaningful — it could indicate a meter offline, a billing error, or a genuinely idle facility. Silently dropping it would misrepresent the data. The analyst sees it, flagged, and decides.

---

## Travel: Distance for Flights

**Ambiguity:** The Concur/Navan export does not always include distance. Sometimes only airport codes are provided.

**Decision:** We compute great-circle distance using the Haversine formula from a hardcoded airport coordinate table (covering 14 major airports in our sample data). If both origin and destination codes are in the table, we calculate distance. If not, we check for a `distance_km` column. If neither works, we flag the record and leave `co2e_kg` null.

**Why not use a live airport distance API?** Adds an external dependency and latency to the ingestion path. For a prototype, the coordinate table covers the airports in the sample data. In production, we'd use the OpenFlights dataset or a maintained IATA lookup.

**Short-haul vs long-haul split:** Flights under 3,700 km use 0.255 kg CO2e/km (DEFRA short-haul), over 3,700 km use 0.195 kg CO2e/km (DEFRA long-haul). The threshold approximates a 3-hour flight at typical cruise speed.

---

## Travel: Hotel Emission Factor

**Ambiguity:** Hotel emissions depend on hotel category, location, and energy mix. Concur data gives us vendor name but not hotel category.

**Decision:** Use a flat rate of 31 kg CO2e per night (DEFRA 2023 average UK hotel, used as a global proxy). Flag that this is an approximation.

**What we'd ask the PM:** Should we differentiate by geography? A Singapore hotel has a different grid mix than a London hotel. If the client wants granular Scope 3 Category 6 reporting, we need a more detailed factor set.

---

## Review and Lock

**Decision:** Approval locks a record permanently. Rejection does not lock — the analyst can reject, the data team can re-ingest a corrected file, and the new record goes through review again.

**Why lock on approval?** Once a record is approved it may be included in a report submitted to auditors or regulators. Allowing post-approval edits would break the chain of custody.

---

## Scope Assignment

**Decision:** All scope assignments are made at parse time by the parser, not by the analyst.

**Why:** The GHG Protocol defines scope by the nature of the activity, not by interpretation. Fuel combustion from owned equipment is always Scope 1. Grid electricity is always Scope 2. Business travel is always Scope 3. We encode this in the parser rather than requiring analysts to categorize manually, reducing error and review burden.

**Exception:** SAP materials that are not identifiable as fuels are assigned Scope 3 / `purchased_goods` and flagged — because we cannot be certain without the material master.

---

## What We'd Ask the PM Before Production

1. Which SAP movement types should we include? (101 = goods receipt, 261 = goods issue to production — both relevant)
2. What grid region per utility site? India is 0.82 but this varies by state.
3. Can the client provide a material master CSV to replace our fuzzy fuel detection?
4. Should hotel emissions be broken out by geography?
5. Is there a materiality threshold below which records don't need individual analyst review?
