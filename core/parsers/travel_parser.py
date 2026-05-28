import pandas as pd
from math import radians, sin, cos, sqrt, atan2
from datetime import datetime

# kg CO2e per km per passenger
TRAVEL_EMISSION_FACTORS = {
    'air_short': 0.255,    # <3h flight
    'air_long': 0.195,     # >3h flight (more efficient per km)
    'hotel': 31.0,         # per night
    'car_rental': 0.171,   # per km
    'taxi': 0.149,         # per km
    'train': 0.041,        # per km
    'default_ground': 0.15,
}

# Major airport lat/long for distance calculation
AIRPORT_COORDS = {
    'DEL': (28.5665, 77.1031), 'BOM': (19.0896, 72.8656),
    'BLR': (13.1986, 77.7066), 'MAA': (12.9941, 80.1709),
    'HYD': (17.2403, 78.4294), 'CCU': (22.6520, 88.4463),
    'LHR': (51.4775, -0.4614), 'CDG': (49.0097, 2.5479),
    'JFK': (40.6413, -73.7781), 'SFO': (37.6213, -122.379),
    'DXB': (25.2532, 55.3657), 'SIN': (1.3644, 103.9915),
    'NRT': (35.7647, 140.3864), 'SYD': (-33.9399, 151.1753),
}

CATEGORY_MAP = {
    'air_travel': 'business_travel_air',
    'flight': 'business_travel_air',
    'hotel': 'business_travel_hotel',
    'taxi': 'business_travel_ground',
    'uber': 'business_travel_ground',
    'car': 'business_travel_ground',
}


def haversine_km(coord1, coord2):
    R = 6371
    lat1, lon1 = map(radians, coord1)
    lat2, lon2 = map(radians, coord2)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


def get_flight_distance(origin, destination):
    o = str(origin).strip().upper()
    d = str(destination).strip().upper()
    if o in AIRPORT_COORDS and d in AIRPORT_COORDS:
        return haversine_km(AIRPORT_COORDS[o], AIRPORT_COORDS[d])
    return None


def normalize_date(val):
    val = str(val).strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(val, fmt).date()
        except ValueError:
            continue
    return None


def classify_expense_type(expense_type_str):
    if not expense_type_str:
        return 'unknown'
    t = str(expense_type_str).lower()
    if any(x in t for x in ['air', 'flight', 'plane', 'airline']):
        return 'air'
    if any(x in t for x in ['hotel', 'lodg', 'accommod', 'motel']):
        return 'hotel'
    if any(x in t for x in ['car', 'rental', 'hire']):
        return 'car_rental'
    if any(x in t for x in ['taxi', 'uber', 'cab', 'ride']):
        return 'taxi'
    if any(x in t for x in ['train', 'rail', 'metro', 'bus']):
        return 'train'
    return 'ground'


def parse_travel_csv(file_obj, tenant, ingestion_job):
    records = []
    errors = []

    try:
        df = pd.read_csv(file_obj, dtype=str)
    except Exception as e:
        return [], [{'row': 0, 'error': f'Could not read file: {str(e)}'}]

    df.columns = [c.strip().lower().replace(' ', '_') for c in df.columns]

    for i, row in df.iterrows():
        raw = {k: str(v) for k, v in row.to_dict().items()}
        row_num = int(i) + 2
        flags = []

        try:
            expense_type = row.get('expense_type') or row.get('type') or row.get('category', '')
            travel_class = classify_expense_type(expense_type)

            travel_date = normalize_date(
                row.get('travel_date') or row.get('date') or row.get('transaction_date', '')
            )

            if travel_class == 'air':
                origin = row.get('origin') or row.get('from') or row.get('departure', '')
                dest = row.get('destination') or row.get('to') or row.get('arrival', '')
                distance_km = get_flight_distance(origin, dest)

                if distance_km is None:
                    # Try to use provided distance column
                    dist_col = row.get('distance_km') or row.get('distance', '')
                    try:
                        distance_km = float(str(dist_col).replace(',', '.'))
                    except (ValueError, TypeError):
                        distance_km = None
                        flags.append(f'Could not calculate distance: {origin} → {dest}')

                if distance_km is not None:
                    ef_key = 'air_long' if distance_km > 3700 else 'air_short'
                    ef = TRAVEL_EMISSION_FACTORS[ef_key]
                    co2e_kg = distance_km * ef
                    normalized_value = distance_km
                    normalized_unit = 'km'
                else:
                    ef = None
                    co2e_kg = None
                    normalized_value = None
                    normalized_unit = 'km'

                category = 'business_travel_air'

            elif travel_class == 'hotel':
                nights_str = str(row.get('nights') or row.get('duration') or row.get('quantity', '1')).strip()
                try:
                    nights = float(nights_str)
                except (ValueError, TypeError):
                    nights = 1
                    flags.append('Could not parse nights — defaulting to 1')

                ef = TRAVEL_EMISSION_FACTORS['hotel']
                co2e_kg = nights * ef
                normalized_value = nights
                normalized_unit = 'nights'
                category = 'business_travel_hotel'

            else:
                dist_str = str(row.get('distance_km') or row.get('distance', '')).strip()
                try:
                    distance_km = float(dist_str.replace(',', '.'))
                except (ValueError, TypeError):
                    distance_km = None
                    flags.append('No distance provided for ground transport')

                ef = TRAVEL_EMISSION_FACTORS.get(travel_class, TRAVEL_EMISSION_FACTORS['default_ground'])
                co2e_kg = distance_km * ef if distance_km else None
                normalized_value = distance_km
                normalized_unit = 'km'
                category = 'business_travel_ground'

            raw_val = str(row.get('amount') or row.get('quantity') or row.get('distance_km', ''))

            records.append({
                'tenant': tenant,
                'ingestion_job': ingestion_job,
                'scope': '3',
                'category': category,
                'raw_activity_value': raw_val,
                'raw_unit': str(expense_type),
                'raw_payload': raw,
                'normalized_value': normalized_value,
                'normalized_unit': normalized_unit,
                'emission_factor': ef,
                'emission_factor_source': 'DEFRA 2023 business travel',
                'co2e_kg': co2e_kg,
                'activity_date': travel_date,
                'is_flagged': bool(flags),
                'flag_reason': '; '.join(flags),
            })

        except Exception as e:
            errors.append({'row': row_num, 'error': str(e)})

    return records, errors