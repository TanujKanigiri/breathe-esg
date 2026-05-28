import pandas as pd
from datetime import datetime
import re

# Emission factors kg CO2e per liter
FUEL_EMISSION_FACTORS = {
    'diesel': 2.68,
    'petrol': 2.31,
    'gasoline': 2.31,
    'natural_gas': 2.04,
    'hsd': 2.68,  # High Speed Diesel — common SAP label
}

# Unit normalization to liters
UNIT_TO_LITERS = {
    'l': 1.0, 'ltr': 1.0, 'litre': 1.0, 'liters': 1.0, 'litres': 1.0,
    'gal': 3.785, 'gallon': 3.785, 'gallons': 3.785,
    'm3': 1000.0, 'cum': 1000.0,
    'kg': 1.0,  # for gas sold by weight — treat 1:1 as approximation
}

# SAP column name mappings (German and English variants)
COLUMN_MAP = {
    'budat': 'posting_date', 'buchungsdatum': 'posting_date',
    'werks': 'plant_code', 'werk': 'plant_code',
    'matnr': 'material_number', 'materialnummer': 'material_number',
    'maktx': 'material_desc', 'bezeichnung': 'material_desc',
    'menge': 'quantity', 'mng': 'quantity',
    'meins': 'unit', 'einheit': 'unit',
    'lifnr': 'vendor_id', 'lieferant': 'vendor_id',
    'bwart': 'movement_type',
}


def normalize_date(val):
    val = str(val).strip()
    for fmt in ('%d.%m.%Y', '%Y%m%d', '%Y-%m-%d', '%m/%d/%Y'):
        try:
            return datetime.strptime(val, fmt).date()
        except ValueError:
            continue
    return None

def detect_fuel_type(material_desc):
    if not material_desc:
        return None

    desc = str(material_desc).lower()

    if 'diesel' in desc or 'hsd' in desc:
        return 'diesel'

    if 'petrol' in desc or 'gasoline' in desc:
        return 'petrol'

    if 'natural gas' in desc or 'lng' in desc or 'cng' in desc:
        return 'natural_gas'

    return None
print(detect_fuel_type("Diesel Fuel HSD"))
print(detect_fuel_type("Petrol Gasoline"))
print(detect_fuel_type("Natural Gas LNG"))

def parse_sap_csv(file_obj, tenant, ingestion_job):
    records = []
    errors = []

    try:
        df = pd.read_csv(file_obj, sep=None, engine='python', dtype=str)
    except Exception as e:
        return [], [{'row': 0, 'error': f'Could not read file: {str(e)}'}]

    # Normalize column names
    df.columns = [COLUMN_MAP.get(c.strip().lower(), c.strip().lower()) for c in df.columns]

    required = ['quantity', 'unit']
    for col in required:
        if col not in df.columns:
            return [], [{'row': 0, 'error': f'Missing required column: {col}'}]

    for i, row in df.iterrows():
        raw = row.to_dict()
        row_num = i + 2  # 1-indexed + header

        try:
            qty_str = str(row.get('quantity', '')).replace(',', '.').strip()
            if not qty_str or qty_str == 'nan':
                errors.append({'row': row_num, 'error': 'Empty quantity'})
                continue

            qty = float(qty_str)
            unit = str(row.get('unit', '')).strip().lower()
            material_desc = row.get('material_desc', '')
            posting_date = normalize_date(row.get('posting_date', ''))

            # Normalize to liters
            multiplier = UNIT_TO_LITERS.get(unit, None)
            flags = []
            flag_reason = ''

            if multiplier is None:
                flags.append(f'Unrecognized unit: {unit}')
                normalized_value = qty
                normalized_unit = unit
            else:
                normalized_value = qty * multiplier
                normalized_unit = 'liters'

            fuel_type = detect_fuel_type(material_desc)
            print("MATERIAL:", material_desc)
            print("ROW:", raw)
            print("FUEL TYPE:", fuel_type)
            if fuel_type is None:
                flags.append(f'Could not determine fuel type from: {material_desc}')
                co2e_kg = None
                ef = None
                ef_source = 'unknown'
            else:
                ef = FUEL_EMISSION_FACTORS[fuel_type]
                co2e_kg = normalized_value * ef
                ef_source = f'DEFRA 2023 — {fuel_type}'

            # Flag suspicious values
            if normalized_value > 50000:
                flags.append('Quantity unusually high (>50,000 liters)')

            if flags:
                flag_reason = '; '.join(flags)

            # Determine scope: fuel combustion = Scope 1
            # Purchased goods (non-fuel) = Scope 3
            movement_type = str(raw.get('movement_type', '')).strip()
            is_fuel = fuel_type is not None
            scope = '1' if is_fuel else '3'
            category = 'fuel_combustion' if is_fuel else 'purchased_goods'

            records.append({
                'tenant': tenant,
                'ingestion_job': ingestion_job,
                'scope': scope,
                'category': category,
                'raw_activity_value': qty_str,
                'raw_unit': unit,
                'raw_payload': raw,
                'normalized_value': normalized_value,
                'normalized_unit': normalized_unit,
                'emission_factor': ef,
                'emission_factor_source': ef_source,
                'co2e_kg': co2e_kg,
                'activity_date': posting_date,
                'is_flagged': bool(flags),
                'flag_reason': flag_reason,
            })

        except Exception as e:
            errors.append({'row': row_num, 'error': str(e)})

    return records, errors