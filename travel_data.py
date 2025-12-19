"""
Free travel data integrations (no API keys needed)
- Destination autocomplete: Geoapify (free tier - 3000 req/day)
- Weather: Open-Meteo (fully free, no key)
- Timezone: WorldTimeAPI (fully free, no key)
"""

import requests
from functools import lru_cache
import logging
import urllib3
import os
from typing import Optional, List
from urllib.parse import quote

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

# Free APIs (no keys required)
OPEN_METEO_URL = "https://api.open-meteo.com/v1"
GEONAMES_TIMEZONE_URL = "http://api.geonames.org/timezoneJSON"
GEONAMES_USERNAME = "demo"  # Free tier username
RESTCOUNTRIES_URL = "https://restcountries.com/v3.1"
TRAVEL_ADVISORY_URL = "https://www.travel-advisory.info/api"
EXCHANGERATE_URL = "https://api.exchangerate-api.com/v4/latest"
GEOAPIFY_PLACES_URL = "https://api.geoapify.com/v2/places"
GEOAPIFY_AUTOCOMPLETE_URL = "https://api.geoapify.com/v1/geocode/autocomplete"
NOMINATIM_AUTOCOMPLETE_URL = "https://nominatim.openstreetmap.org/search"
DEFAULT_POI_RADIUS = 2500
DEFAULT_POI_LIMIT = 15
DEFAULT_POI_KINDS = [
    'cultural', 'historic', 'museums', 'natural', 'parks',
    'foods', 'restaurants', 'shops', 'sport', 'interesting_places'
]

HOTEL_KINDS = ['hotels', 'hostels', 'guest_houses']

DEFAULT_POI_CATEGORIES = [
    'tourism.sights',
    'tourism.attraction',
    'entertainment.culture',
    'catering.restaurant',
    'catering.cafe',
    'leisure.park'
]

KIND_CATEGORY_MAP = {
    'foods': ['catering.restaurant', 'catering.fast_food'],
    'restaurants': ['catering.restaurant'],
    'cafes': ['catering.cafe'],
    'cultural': ['entertainment.culture', 'tourism.sights'],
    'historic': ['heritage.sights', 'tourism.sights'],
    'museums': ['entertainment.museum'],
    'natural': ['natural', 'tourism.sights'],
    'parks': ['leisure.park'],
    'shops': ['commercial.shopping_mall', 'commercial.shopping_center'],
    'sport': ['sport.sport_center'],
    'interesting_places': ['tourism.attraction'],
    'beaches': ['natural.beach'],
    'mountains': ['natural.mountain'],
    'hotels': ['accommodation.hotel'],
    'hostels': ['accommodation.hostel'],
    'guest_houses': ['accommodation.guest_house'],
}

LOCAL_COUNTRY_OVERRIDES = {
    'india': {
        'name': 'India',
        'capital': 'New Delhi',
        'region': 'Asia',
        'subregion': 'Southern Asia',
        'population': 1380004385,
        'area': 3287263,
        'currency_code': 'INR',
        'currency_name': 'Indian Rupee',
        'currency_symbol': '₹',
        'languages': ['Hindi', 'English'],
        'country_code': 'IN',
        'country_code3': 'IND',
        'timezones': ['Asia/Kolkata'],
        'flag': 'https://flagcdn.com/w320/in.png'
    }
}


@lru_cache(maxsize=100)
def autocomplete_destination(query: str, limit: int = 10):
    """Autocomplete destinations via Geoapify, fallback to local list."""
    if not query:
        return []

    query = query.strip()
    if len(query) < 2:
        return []

    api_key = os.getenv('GEOAPIFY_API_KEY')
    if api_key:
        try:
            geoapify_results = _geoapify_autocomplete(query, limit, api_key)
            if geoapify_results:
                return geoapify_results
        except Exception as exc:
            logger.warning(f"Geoapify autocomplete failed, trying Nominatim: {exc}")

    try:
        nominatim_results = _nominatim_autocomplete(query, limit)
        if nominatim_results:
            return nominatim_results
    except Exception as exc:
        logger.warning(f"Nominatim autocomplete failed, using fallback: {exc}")

    return _fallback_autocomplete(query.lower(), limit)


def _fallback_autocomplete(query: str, limit: int = 10):
    """Hardcoded major cities as fallback"""
    cities = [
        {'name': 'Paris', 'country': 'France', 'lat': 48.8566, 'lon': 2.3522},
        {'name': 'London', 'country': 'United Kingdom', 'lat': 51.5074, 'lon': -0.1278},
        {'name': 'New York', 'country': 'United States', 'lat': 40.7128, 'lon': -74.0060},
        {'name': 'Tokyo', 'country': 'Japan', 'lat': 35.6762, 'lon': 139.6503},
        {'name': 'Dubai', 'country': 'United Arab Emirates', 'lat': 25.2048, 'lon': 55.2708},
        {'name': 'Barcelona', 'country': 'Spain', 'lat': 41.3851, 'lon': 2.1734},
        {'name': 'Rome', 'country': 'Italy', 'lat': 41.9028, 'lon': 12.4964},
        {'name': 'Amsterdam', 'country': 'Netherlands', 'lat': 52.3676, 'lon': 4.9041},
        {'name': 'Berlin', 'country': 'Germany', 'lat': 52.5200, 'lon': 13.4050},
        {'name': 'Sydney', 'country': 'Australia', 'lat': -33.8688, 'lon': 151.2093},
        {'name': 'Singapore', 'country': 'Singapore', 'lat': 1.3521, 'lon': 103.8198},
        {'name': 'Bangkok', 'country': 'Thailand', 'lat': 13.7563, 'lon': 100.5018},
        {'name': 'Mumbai', 'country': 'India', 'lat': 19.0760, 'lon': 72.8777},
        {'name': 'Istanbul', 'country': 'Turkey', 'lat': 41.0082, 'lon': 28.9784},
        {'name': 'Los Angeles', 'country': 'United States', 'lat': 34.0522, 'lon': -118.2437},
        {'name': 'Toronto', 'country': 'Canada', 'lat': 43.6532, 'lon': -79.3832},
        {'name': 'Mexico City', 'country': 'Mexico', 'lat': 19.4326, 'lon': -99.1332},
        {'name': 'Rio de Janeiro', 'country': 'Brazil', 'lat': -22.9068, 'lon': -43.1729},
        {'name': 'Cairo', 'country': 'Egypt', 'lat': 30.0444, 'lon': 31.2357},
        {'name': 'Cape Town', 'country': 'South Africa', 'lat': -33.9249, 'lon': 18.4241},
    ]
    
    # Filter cities matching query
    matches = [c for c in cities if query in c['name'].lower() or query in c['country'].lower()]
    return matches[:limit]


def _geoapify_autocomplete(query: str, limit: int, api_key: str):
    params = {
        'text': query,
        'limit': max(1, min(limit, 20)),
        'lang': 'en',
        'apiKey': api_key
    }

    response = requests.get(
        GEOAPIFY_AUTOCOMPLETE_URL,
        params=params,
        timeout=8
    )
    response.raise_for_status()
    data = response.json()

    features = data.get('features', [])
    if not features:
        return []

    results = []
    for feature in features:
        props = feature.get('properties', {})
        geometry = feature.get('geometry', {})
        coords = geometry.get('coordinates', [])

        lat = props.get('lat') or (coords[1] if len(coords) == 2 else None)
        lon = props.get('lon') or (coords[0] if len(coords) == 2 else None)
        if lat is None or lon is None:
            continue

        name = props.get('city') or props.get('name') or props.get('address_line1') or props.get('formatted')
        if not name:
            continue

        results.append({
            'name': name,
            'country': props.get('country', ''),
            'state': props.get('state', ''),
            'lat': lat,
            'lon': lon,
            'display_name': props.get('formatted', name),
            'source': 'geoapify'
        })

        if len(results) >= limit:
            break

    return results


def _nominatim_autocomplete(query: str, limit: int):
    params = {
        'q': query,
        'format': 'json',
        'limit': max(1, min(limit, 10)),
        'addressdetails': 1
    }

    headers = {'User-Agent': 'TravelPlanner/1.0 (demo@example.com)'}

    response = requests.get(
        NOMINATIM_AUTOCOMPLETE_URL,
        params=params,
        headers=headers,
        timeout=8
    )
    response.raise_for_status()
    data = response.json()

    results = []
    for entry in data:
        lat = float(entry.get('lat', 0))
        lon = float(entry.get('lon', 0))
        if not lat or not lon:
            continue

        address = entry.get('address', {})
        name = address.get('city') or address.get('town') or address.get('state') or entry.get('display_name')
        if not name:
            continue

        results.append({
            'name': name,
            'country': address.get('country', ''),
            'state': address.get('state', ''),
            'lat': lat,
            'lon': lon,
            'display_name': entry.get('display_name', name),
            'source': 'nominatim'
        })

        if len(results) >= limit:
            break

    return results


@lru_cache(maxsize=200)
def get_weather(lat: float, lon: float, days: int = 7):
    """
    Get weather forecast using Open-Meteo (completely free, no key needed).
    Returns daily forecast for temperature, precipitation, etc.
    """
    try:
        response = requests.get(
            f"{OPEN_METEO_URL}/forecast",
            params={
                'latitude': lat,
                'longitude': lon,
                'daily': 'temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode',
                'forecast_days': min(days, 16),  # Open-Meteo limit is 16 days
                'timezone': 'auto'
            },
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        
        # Transform to simpler format
        daily = data.get('daily', {})
        forecasts = []
        for i in range(len(daily.get('time', []))):
            forecasts.append({
                'date': daily['time'][i],
                'temp_max': daily['temperature_2m_max'][i],
                'temp_min': daily['temperature_2m_min'][i],
                'precipitation': daily['precipitation_sum'][i],
                'weathercode': daily['weathercode'][i],
            })
        
        return {
            'location': {'lat': lat, 'lon': lon},
            'timezone': data.get('timezone', 'UTC'),
            'forecasts': forecasts
        }
    except Exception as e:
        logger.error(f"Weather API error: {str(e)}")
        return None


@lru_cache(maxsize=200)
def get_timezone(lat: float, lon: float):
    """
    Get timezone using GeoNames (free tier, demo account).
    Returns timezone info for coordinates.
    """
    try:
        response = requests.get(
            GEONAMES_TIMEZONE_URL,
            params={
                'lat': lat,
                'lng': lon,
                'username': GEONAMES_USERNAME
            },
            timeout=5
        )
        response.raise_for_status()
        data = response.json()
        
        return {
            'timezone': data.get('timezoneId', 'UTC'),
            'gmtOffset': data.get('gmtOffset', 0),
            'dstOffset': data.get('dstOffset', 0),
            'time': data.get('time', ''),
            'countryCode': data.get('countryCode', ''),
            'countryName': data.get('countryName', ''),
        }
    except Exception as e:
        logger.error(f"Timezone API error: {str(e)}")
        return None


@lru_cache(maxsize=100)
def get_country_info(country_name: str):
    """Get country information using RestCountries with accurate matching."""
    if not country_name:
        return None

    normalized_query = country_name.strip()
    if not normalized_query:
        return None

    override_key = normalized_query.lower()

    params = {
        'fullText': 'true',
        'fields': 'name,capital,region,subregion,population,area,currencies,languages,cca2,cca3,flags,timezones'
    }

    try:
        response = requests.get(
            f"{RESTCOUNTRIES_URL}/name/{quote(normalized_query)}",
            params=params,
            timeout=10
        )
        response.raise_for_status()
        countries = response.json()
    except requests.HTTPError:
        # Retry with partial match if fullText fails
        try:
            response = requests.get(
                f"{RESTCOUNTRIES_URL}/name/{quote(normalized_query)}",
                params={'fullText': 'false'},
                timeout=10
            )
            response.raise_for_status()
            countries = response.json()
        except Exception as e:
            logger.error(f"Country info error for '{country_name}': {str(e)}")
            return _get_local_country(override_key)
    except Exception as e:
        logger.error(f"Country info error for '{country_name}': {str(e)}")
        return _get_local_country(override_key)

    if not countries:
        return _get_local_country(override_key)

    target = normalized_query.lower()

    def matches(country_data):
        name_block = country_data.get('name', {})
        candidates = [
            name_block.get('common', ''),
            name_block.get('official', ''),
        ]
        native = name_block.get('nativeName', {}) or {}
        for native_entry in native.values():
            candidates.append(native_entry.get('common', ''))
            candidates.append(native_entry.get('official', ''))
        return any((candidate or '').strip().lower() == target for candidate in candidates if candidate)

    selected = next((c for c in countries if matches(c)), countries[0])

    currencies = selected.get('currencies', {}) or {}
    currency_code = next(iter(currencies.keys()), '')
    currency_info = currencies.get(currency_code, {})

    return {
        'name': selected.get('name', {}).get('common', normalized_query),
        'capital': (selected.get('capital') or ['N/A'])[0],
        'region': selected.get('region', 'N/A'),
        'subregion': selected.get('subregion', 'N/A'),
        'population': selected.get('population', 0),
        'area': selected.get('area', 0),
        'currency_code': currency_code or 'USD',
        'currency_name': currency_info.get('name', 'Unknown'),
        'currency_symbol': currency_info.get('symbol', ''),
        'languages': list((selected.get('languages') or {}).values()),
        'country_code': selected.get('cca2', ''),
        'country_code3': selected.get('cca3', ''),
        'timezones': selected.get('timezones', []),
        'flag': selected.get('flags', {}).get('png', ''),
    }


def _get_local_country(country_key: str):
    entry = LOCAL_COUNTRY_OVERRIDES.get(country_key)
    if entry:
        return dict(entry)
    return None


@lru_cache(maxsize=100)
def get_travel_advisory(country_code: str):
    """
    Get travel advisory using free travel-advisory.info API.
    Returns safety score and advisory message.
    """
    try:
        response = requests.get(
            TRAVEL_ADVISORY_URL,
            timeout=10,
            verify=False  # Bypass SSL certificate error
        )
        response.raise_for_status()
        data = response.json()

        country_data = data.get('data', {}).get(country_code.upper(), {})
        if country_data:
            advisory_score = country_data.get('advisory', {}).get('score', 0)
            advisory_msg = country_data.get('advisory', {}).get('message', 'No advisory')
            
            safety_levels = {
                1: 'Exercise normal precautions',
                2: 'Exercise increased caution',
                3: 'Reconsider travel',
                4: 'Do not travel',
                5: 'Do not travel'
            }
            
            return {
                'country': country_code.upper(),
                'country_name': country_data.get('name', ''),
                'score': advisory_score,
                'level': safety_levels.get(int(advisory_score), 'Unknown'),
                'message': advisory_msg,
                'sources': country_data.get('advisory', {}).get('sources', []),
                'updated': country_data.get('advisory', {}).get('updated', ''),
            }
        return None
    except Exception as e:
        logger.error(f"Travel advisory error for '{country_code}': {str(e)}")
        return None


@lru_cache(maxsize=50)
def get_exchange_rate(from_currency: str = 'USD', to_currency: str = 'EUR'):
    """
    Get currency exchange rates using exchangerate-api.com (completely free).
    Returns current exchange rate between two currencies.
    """
    try:
        # API: https://api.exchangerate-api.com/v4/latest/USD
        response = requests.get(
            f"{EXCHANGERATE_URL}/{from_currency}",
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        
        rates = data.get('rates', {})
        if to_currency in rates:
            return {
                'from': from_currency,
                'to': to_currency,
                'rate': rates[to_currency],
                'date': data.get('date', ''),
                'base': data.get('base', from_currency),
            }
        return None
    except Exception as e:
        logger.error(f"Exchange rate error ({from_currency} -> {to_currency}): {str(e)}")
        return None


def get_pois(lat: float, lon: float, kinds=None, radius: Optional[int] = None,
             limit: Optional[int] = None, api_key: Optional[str] = None):
    """Fetch nearby points of interest using Geoapify Places, ranked by popularity."""
    api_key = api_key or os.getenv('GEOAPIFY_API_KEY')
    if not api_key:
        raise ValueError('Missing Geoapify API key')

    if not lat or not lon:
        raise ValueError('Latitude and longitude are required for POI lookup')

    radius_value = DEFAULT_POI_RADIUS if radius is None else int(radius)
    limit_value = DEFAULT_POI_LIMIT if limit is None else int(limit)

    normalized_radius = max(500, min(radius_value, 5000))
    normalized_limit = max(5, min(limit_value, 18))

    categories = _categories_from_kinds(kinds)
    params = {
        'categories': ','.join(categories),
        'filter': f"circle:{lon},{lat},{normalized_radius}",
        'bias': f"proximity:{lon},{lat}",
        'limit': normalized_limit * 2,
        'apiKey': api_key,
    }

    try:
        response = requests.get(
            GEOAPIFY_PLACES_URL,
            params=params,
            timeout=12
        )
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        logger.error(f"Geoapify places error: {str(e)}")
        return []

    pois = []
    for feature in data.get('features', []):
        properties = feature.get('properties', {})
        geometry = feature.get('geometry', {})
        coords = geometry.get('coordinates') or [None, None]
        name = properties.get('name') or properties.get('address_line1') or properties.get('formatted')
        if not name:
            continue

        categories_raw = properties.get('categories') or categories
        if isinstance(categories_raw, str):
            categories_raw = [c.strip() for c in categories_raw.split(',') if c.strip()]

        pois.append({
            'id': properties.get('place_id') or feature.get('id') or name,
            'name': name,
            'lat': coords[1] if len(coords) >= 2 else None,
            'lon': coords[0] if len(coords) >= 2 else None,
            'dist_m': properties.get('distance'),
            'rate': (properties.get('rank') or {}).get('popularity') or (properties.get('rank') or {}).get('confidence'),
            'kinds': categories_raw,
            'address': properties.get('address_line1') or properties.get('formatted', ''),
            'description': properties.get('place_description') or properties.get('address_line2') or '',
            'image': '',
            'url': properties.get('website') or (properties.get('datasource') or {}).get('url'),
            'source': 'geoapify'
        })

    pois.sort(key=_poi_rank_key)
    return pois[:normalized_limit]


def get_hotels(lat: float, lon: float, radius: Optional[int] = None,
               limit: Optional[int] = None, api_key: Optional[str] = None):
    radius_value = radius or 2000
    limit_value = limit or 6
    return get_pois(
        lat=lat,
        lon=lon,
        kinds=HOTEL_KINDS,
        radius=radius_value,
        limit=limit_value,
        api_key=api_key,
    )


def _normalize_kind_list(kinds) -> List[str]:
    if not kinds:
        return []
    if isinstance(kinds, str):
        items = [item.strip() for item in kinds.split(',') if item.strip()]
        return items
    result = []
    for item in kinds:
        if not item:
            continue
        result.append(str(item).strip())
    return result


def _categories_from_kinds(kinds) -> List[str]:
    normalized = _normalize_kind_list(kinds) or DEFAULT_POI_KINDS
    categories: List[str] = []
    for kind in normalized:
        mapped = KIND_CATEGORY_MAP.get(kind.lower())
        if mapped:
            categories.extend(mapped)
    if not categories:
        categories = DEFAULT_POI_CATEGORIES
    return list(dict.fromkeys(categories))


def _poi_rank_key(poi):
    try:
        rate = float(poi.get('rate') or 0)
    except (TypeError, ValueError):
        rate = 0.0
    try:
        dist = float(poi.get('dist_m')) if poi.get('dist_m') is not None else float('inf')
    except (TypeError, ValueError):
        dist = float('inf')
    return (-rate, dist)

def get_travel_advisories(country_code: str):
    """
    Alias for backward compatibility
    """
    return get_travel_advisory(country_code)
