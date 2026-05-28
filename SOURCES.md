# SOURCES

For each of the three data sources: what real-world format we researched, what we learned, what our sample data looks like and why, and what would break in a real deployment.

---

## Source 1: SAP Fuel and Procurement Data

### What we researched

SAP exposes goods movement data primarily through transaction MB51 (Material Document List) and MB52 (Warehouse Stocks). In a real enterprise, the sustainability team runs MB51 with a date range filter and exports to a spreadsheet or flat file. The export format is configurable — some clients get column headers in English, some in German (depending on SAP system language settings), some get a mix if they've customized their layouts.

We looked at the standard MB51 output fields: `WERKS` (plant), `MATNR` (material number), `MAKTX` (material description — from the material master), `MENGE` (quantity), `MEINS` (unit of measure), `BUDAT` (posting date), `LIFNR` (vendor number), `BWART` (movement type). These are the standard field names in SAP technical documentation for table `MSEG` (material document segment), which backs MB51.

Dates in SAP default to `DD.MM.YYYY` format — the German locale standard — regardless of where the client is located, because SAP was built in Germany and many installations retain this default.

Units come from SAP's internal unit of measure table (`T006`): `L` for liters, `M3` for cubic meters, `KG` for kilograms, `G` for grams. Clients don't always convert these to consistent units before export.

Movement type 101 is goods receipt against a purchase order. 261 is goods issue to a production order. For fuel tracking, 101 captures procurement; 261 captures consumption. We chose 101 (receipt) as our focus, meaning our data reflects what was purchased, not what was burned — a legitimate proxy for Scope 1 when consumption data is unavailable.

### What our sample data looks like and why

```
WERKS,MATNR,MAKTX,MENGE,MEINS,BUDAT,LIFNR,BWART
1001,MAT-001,Diesel Fuel HSD,5000,L,01.03.2024,VEND-042,101
```

- **German date format** (`01.03.2024`): realistic, matches SAP default locale
- **Plant codes** (`1001`, `1002`, `1003`): opaque numeric codes that mean nothing without a plant master — realistic, intentionally left unmapped
- **`HSD`** (High Speed Diesel): the Indian standard term for road diesel, used in SAP configurations for Indian manufacturing clients
- **Mixed units** (`L`, `M3`, `KG`): `L` for liquid fuels, `M3` for natural gas (sold by volume in India), `KG` for lubricants and some specialty products
- **`MAT-008 Unknown Lubricant`**: a material whose description does not match any fuel keyword — intentional, to test our flagging logic
- **`MAT-009` with 92,000L**: a statistically anomalous value — 13× the next largest diesel delivery from the same plant — to test outlier flagging

### What would break in a real deployment

1. **Material master dependency**: We detect fuel type from `MAKTX` text. Real SAP clients have material descriptions like `"FUEL-D-EXT-HS50"` or `"PRD-LUB-GP46"` — internal codes that cannot be parsed without the material master table mapping MATNR to commodity type. Our fuzzy matching would fail on most rows.

2. **Plant master dependency**: `WERKS` values like `1001` are meaningless without a plant master that maps them to site names, geographies, and applicable emission factors. We store them in `raw_payload` but cannot enrich them.

3. **Currency and cost data**: MB51 exports don't always include cost. When they do, it may be in local currency with exchange rates not in the file. We ignore cost entirely.

4. **Multi-company codes**: Large enterprises have multiple SAP company codes, each with its own MB51. A full ingestion would require merging exports across company codes and deduplicating by document number.

5. **Retroactive corrections**: SAP allows reversal documents (movement type 102 reverses 101). If a reversal arrives after the original has been approved, our system has no way to handle it without the re-ingestion/versioning logic described in TRADEOFFS.md.

---

## Source 2: Utility Electricity Data

### What we researched

Utility billing data reaches facilities teams in three ways: PDF bills (most common for small sites), portal CSV exports (available from most major utilities for commercial accounts), and Green Button API (structured XML/JSON, available from some US utilities, almost none in India).

We chose portal CSV because it is the most structured format a facilities manager can pull without IT involvement, and it is available from virtually all commercial utility providers globally — BESCOM (Bangalore), TSSPDCL (Hyderabad), MSEDCL (Maharashtra), and equivalents.

A typical utility portal CSV export contains: account number, meter ID, site description, commodity type, unit of measure (kWh or MWh), billing period start, billing period end, usage quantity, peak demand (kW), and total cost. Some portals export one row per meter per billing period; others export one row per billing period with all meters for an account.

Billing periods do not align to calendar months. A meter read on February 1 and March 4 (33 days) is normal. Tariff structures for commercial accounts often include demand charges (peak kW), energy charges (kWh consumed), and fuel adjustment surcharges — none of which affect our kWh normalization but all of which appear in the CSV as extra columns.

Indian grid emission factor: Central Electricity Authority (CEA) publishes CO2 baseline database for the Indian grid. The 2023 figure for the national grid is approximately 0.82 kg CO2e/kWh. State-level factors vary (coal-heavy states like Jharkhand are higher; hydro-heavy states like Himachal Pradesh are lower). We use the national average as a default and allow the grid region to be specified per upload.

### What our sample data looks like and why

```
account_number,meter_id,site,commodity,unit,bill_start_date,bill_end_date,usage,demand,cost
ACC-001,MTR-HQ-01,HQ Building,electric,kwh,2024-02-01,2024-03-04,42500,120,3200.00
ACC-002,MTR-WH-02,Warehouse B,electric,mwh,2024-02-03,2024-03-05,55.4,0,4200.00
ACC-003,MTR-FAC-02,Factory Floor,electric,kwh,2024-02-01,2024-03-03,0,0,0.00
```

- **Mixed units** (`kwh` and `mwh`): realistic — different portals default to different units, and some large-consumption meters are configured to report in MWh
- **Non-calendar billing periods** (Feb 1 → Mar 4): realistic meter reading cycles
- **Zero row** (`MTR-FAC-02`): realistic — a meter that wasn't read, was offline, or the facility was idle
- **`demand` column with zero for MWh meter**: realistic — some tariff structures don't include demand charges for sub-threshold accounts

### What would break in a real deployment

1. **PDF bills**: Most small sites don't get portal CSV access. Their bills are PDFs. Parsing PDFs reliably across utility formats is unsolved at scale.

2. **Multi-site account aggregation**: Some accounts cover multiple physical sites on one invoice. Our model stores meter-level data but the CSV may not always provide meter IDs — just a single account total.

3. **Tariff decomposition**: Demand charges (kW) represent the client's peak draw, not consumption. They don't translate to kWh. Some emission methodologies require separating consumption from demand — we don't do this.

4. **Green Button**: US-based clients may have Green Button access, which provides interval data (15-minute readings) rather than monthly summaries. Our model can't handle time-series interval data without schema changes.

5. **RECs and PPAs**: Clients with Renewable Energy Certificates or Power Purchase Agreements need to subtract renewable consumption from their Scope 2 totals. We have no mechanism for this.

---

## Source 3: Corporate Travel Data (Concur / Navan)

### What we researched

Corporate travel management platforms like Concur SAP, Navan (formerly TripActions), and Egencia expose expense data via API and as CSV exports. The Concur standard export format is a flat expense report: one row per expense line, with fields for expense type, date, amount, currency, merchant, and — for travel — origin, destination, and sometimes distance.

Key findings from reviewing Concur API documentation and Navan export formats:
- Expense type categorization is user-defined in most implementations. "Air Travel", "Airfare", "Flight", "International Flight" may all mean the same thing depending on how the client configured their expense categories.
- Airport codes (IATA 3-letter) are provided for flights when booked through the platform. If booked outside the platform and expensed manually, origin/destination may be city names or free text.
- Distance is rarely provided. Platforms like Navan are adding carbon fields, but most enterprise Concur configurations don't include them.
- Hotels provide check-in date and number of nights when booked through the platform, but not always when manually expensed.
- Ground transport (taxi, car rental) almost never includes distance — only amount and currency.

Emission factors: We use DEFRA 2023 GHG Conversion Factors for Company Reporting, which is the standard reference for UK-registered companies and widely used internationally. For flights: 0.255 kg CO2e/km (short-haul economy) and 0.195 kg CO2e/km (long-haul economy). For hotels: 31.0 kg CO2e/night. For car rental: 0.171 kg CO2e/km. For taxi: 0.149 kg CO2e/km. For rail: 0.041 kg CO2e/km.

### What our sample data looks like and why

```
expense_type,travel_date,origin,destination,traveler_name,vendor,amount,currency,nights,distance_km
Air Travel,2024-03-05,DEL,BOM,Priya Sharma,IndiGo,4500,INR,,,
Hotel,2024-03-08,,London,Rahul Mehta,Marriott London,18000,INR,3,,
Taxi,2024-03-06,,,Priya Sharma,Uber,850,INR,,12
Car Rental,2024-03-09,,,Rahul Mehta,Hertz London,12000,INR,,280
```

- **IATA airport codes** (`DEL`, `BOM`, `LHR`, `SIN`): realistic — Concur uses IATA codes for booked flights
- **Empty origin/destination for hotels**: realistic — hotels don't have origin/destination, just city
- **Empty distance for taxi**: realistic — taxi expenses in Concur rarely include distance, only amount
- **`distance_km` provided for car rental**: realistic when the booking platform captures it; not always available
- **Mixed domestic and international**: `DEL-BOM` (short-haul, ~1,150 km) vs `BOM-LHR` (long-haul, ~7,200 km) — tests our short/long-haul threshold
- **INR currency**: all expenses in INR but our model stores raw amount in native currency, not converted — we don't use amount for emission calculation, only for financial reporting

### What would break in a real deployment

1. **Unknown airport codes**: Our coordinate table covers 14 airports. A real deployment needs all ~9,000 IATA airports. We'd use the OpenFlights dataset or an IATA API lookup.

2. **Expense type inconsistency**: If the client's Concur configuration uses "International Air" and "Domestic Air" as separate expense types, our classifier needs to be extended. The current keyword matching covers common variants but not all.

3. **Class of travel**: DEFRA factors differ significantly by cabin class — business class flights emit roughly 2.9× more than economy per passenger. Concur data includes class when booked through the platform but not for manually expensed tickets. We use economy as default.

4. **Currency conversion**: We store `amount` in native currency (`raw_payload`) but don't convert it. If a client needs spend-based Scope 3 calculations (Category 6 alternative method), currency conversion and exchange rate data would be required.

5. **Layered itineraries**: A trip from HYD to JFK via DXB appears as two flight rows in Concur. Our model treats them as two separate records, which is correct for emissions but requires the analyst to understand that the two rows are one trip.

6. **Navan vs Concur field names**: The two platforms use different column headers for equivalent fields. Our parser normalizes column names but only covers the patterns in our sample. A real deployment would need a per-client field mapping configuration stored in `DataSource.config`.
