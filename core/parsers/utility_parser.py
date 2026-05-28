import pandas as pd
from datetime import datetime

# kg CO2e per kWh by region (grid emission factors)
GRID_EMISSION_FACTORS = {
    'IN': 0.82,   # India
    'US': 0.386,
    'UK': 0.233,
    'EU': 0.276,
    'default': 0.5,
}

UNIT_TO_KWH = {
    'kwh': 1.0,
    'mwh': 1000.0,
    'kbtu': 0.2931,
    'wh': 0.001,
}


def normalize_date(val):
    val = str(val).strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y', '%b %Y', '%B %Y'):
        try:
            return datetime.strptime(val, fmt).date()
        except ValueError:
            continue
    return None


def parse_utility_csv(file_obj, tenant, ingestion_job, grid_region='default'):
    records = []
    errors = []

    try:
        df = pd.read_csv(file_obj, dtype=str)
    except Exception as e:
        return [], [{'row': 0, 'error': f'Could not read file: {str(e)}'}]

    df.columns = [c.strip().lower().replace(' ', '_') for c in df.columns]

    # Accept flexible column names
    col_map = {}
    for col in df.columns:
        if any(x in col for x in ['kwh', 'usage', 'consumption', 'use']):
            col_map['usage'] = col
        if any(x in col for x in ['start', 'from', 'bill_start', 'period_start']):
            col_map['period_start'] = col
        if any(x in col for x in ['end', 'to', 'bill_end', 'period_end', 'read_date']):
            col_map['period_end'] = col
        if any(x in col for x in ['meter', 'account', 'site']):
            col_map['meter_id'] = col
        if 'unit' in col:
            col_map['unit'] = col

    if 'usage' not in col_map:
        return [], [{'row': 0, 'error': 'No usage/kWh column found'}]

    ef = GRID_EMISSION_FACTORS.get(grid_region, GRID_EMISSION_FACTORS['default'])

    for i, row in df.iterrows():
        raw = row.to_dict()
        row_num = i + 2

        try:
            usage_str = str(row.get(col_map['usage'], '')).replace(',', '.').strip()
            if not usage_str or usage_str == 'nan':
                errors.append({'row': row_num, 'error': 'Empty usage value'})
                continue

            usage = float(usage_str)

            unit_col = col_map.get('unit')
            unit = str(row.get(unit_col, 'kwh')).strip().lower() if unit_col else 'kwh'
            multiplier = UNIT_TO_KWH.get(unit, None)

            flags = []
            if multiplier is None:
                flags.append(f'Unrecognized unit: {unit}')
                kwh = usage
            else:
                kwh = usage * multiplier

            co2e_kg = kwh * ef

            period_end_col = col_map.get('period_end')
            activity_date = normalize_date(row.get(period_end_col, '')) if period_end_col else None

            # Flag outliers
            if kwh > 500000:
                flags.append('Usage unusually high (>500,000 kWh)')
            if kwh <= 0:
                flags.append('Zero or negative usage')

            records.append({
                'tenant': tenant,
                'ingestion_job': ingestion_job,
                'scope': '2',
                'category': 'electricity',
                'raw_activity_value': usage_str,
                'raw_unit': unit,
                'raw_payload': raw,
                'normalized_value': kwh,
                'normalized_unit': 'kwh',
                'emission_factor': ef,
                'emission_factor_source': f'IEA 2023 grid factor — {grid_region}',
                'co2e_kg': co2e_kg,
                'activity_date': activity_date,
                'is_flagged': bool(flags),
                'flag_reason': '; '.join(flags),
            })

        except Exception as e:
            errors.append({'row': row_num, 'error': str(e)})

    return records, errors