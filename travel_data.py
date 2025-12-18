"""
Free travel data integrations (no API keys needed)
- Destination autocomplete: Geoapify (free tier - 3000 req/day)
- Weather: Open-Meteo (fully free, no key)
- Timezone: WorldTimeAPI (fully free, no key)
"""

import requests
import json
from functools import lru_cache
import logging
import urllib3
import os
from typing import Optional
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
OPENTRIPMAP_BASE_URL = "https://api.opentripmap.com/0.1/en/places"
OPENROUTESERVICE_BASE_URL = "https://api.openrouteservice.org/v2/directions"
GEOAPIFY_AUTOCOMPLETE_URL = "https://api.geoapify.com/v1/geocode/autocomplete"
NOMINATIM_AUTOCOMPLETE_URL = "https://nominatim.openstreetmap.org/search"
DEFAULT_POI_RADIUS = 2500
DEFAULT_POI_LIMIT = 15
DEFAULT_POI_KINDS = [
    'cultural', 'historic', 'museums', 'natural', 'parks',
    'foods', 'restaurants', 'shops', 'sport', 'interesting_places'
]

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
    """Fetch nearby points of interest using OpenTripMap."""
    api_key = api_key or os.getenv('OPENTRIPMAP_API_KEY')
    if not api_key:
        raise ValueError('Missing OpenTripMap API key')

    if not lat or not lon:
        raise ValueError('Latitude and longitude are required for POI lookup')

    radius_value = DEFAULT_POI_RADIUS if radius is None else int(radius)
    limit_value = DEFAULT_POI_LIMIT if limit is None else int(limit)

    normalized_radius = max(500, min(radius_value, 5000))
    normalized_limit = max(5, min(limit_value, 18))

    params = {
        'lat': lat,
        'lon': lon,
        'radius': normalized_radius,
        'limit': normalized_limit * 2,  # request extra, filter later
        'format': 'geojson',
        'apikey': api_key,
        'rate': 3  # prioritize well-rated spots
    }

    if kinds:
        if isinstance(kinds, (list, tuple, set)):
            params['kinds'] = ','.join(sorted({k for k in kinds if k}))
        else:
            params['kinds'] = kinds
    else:
        params['kinds'] = ','.join(DEFAULT_POI_KINDS)

    try:
        response = requests.get(
            f"{OPENTRIPMAP_BASE_URL}/radius",
            params=params,
            timeout=12
        )
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        logger.error(f"OpenTripMap radius error: {str(e)}")
        return []

    pois = []
    details_loaded = 0

    for feature in data.get('features', []):
        properties = feature.get('properties', {})
        geometry = feature.get('geometry', {})
        name = properties.get('name')
        xid = properties.get('xid')

        if not name or not geometry:
            continue

        poi = {
            'id': xid or name,
            'name': name,
            'lat': geometry.get('coordinates', [None, None])[1],
            'lon': geometry.get('coordinates', [None, None])[0],
            'dist_m': properties.get('dist'),
            'rate': properties.get('rate'),
            'kinds': properties.get('kinds', '').split(',') if properties.get('kinds') else [],
            'address': '',
            'description': '',
            'image': '',
            'url': properties.get('otm')
        }

        if xid and details_loaded < normalized_limit:
            detail = _get_poi_details(xid, api_key)
            if detail:
                poi['description'] = (
                    detail.get('wikipedia_extracts', {}).get('text') or
                    detail.get('info', {}).get('descr', '')
                )
                preview = detail.get('preview') or {}
                poi['image'] = preview.get('source', '')
                poi['url'] = detail.get('otm', detail.get('wikipedia', poi['url']))
                address = detail.get('address', {})
                components = [
                    address.get('road'),
                    address.get('house_number'),
                    address.get('city'),
                    address.get('state'),
                    address.get('country')
                ]
                poi['address'] = ', '.join(filter(None, components))
            details_loaded += 1

        pois.append(poi)
        if len(pois) >= normalized_limit:
            break

    return pois


def _get_poi_details(xid: str, api_key: str):
    try:
        response = requests.get(
            f"{OPENTRIPMAP_BASE_URL}/xid/{xid}",
            params={'apikey': api_key},
            timeout=10
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.warning(f"OpenTripMap detail error ({xid}): {str(e)}")
        return None


def get_route_directions(source: dict, destination: dict, profile: str = 'driving-car',
                         api_key: Optional[str] = None):
    """Fetch a route between two coordinates using OpenRouteService."""
    api_key = api_key or os.getenv('ORS_API_KEY')
    if not api_key:
        raise ValueError('Missing OpenRouteService API key')

    if not source or not destination:
        raise ValueError('Source and destination coordinates are required')

    try:
        payload = {
            'coordinates': [
                [float(source['lon']), float(source['lat'])],
                [float(destination['lon']), float(destination['lat'])]
            ]
        }
    except (KeyError, TypeError, ValueError):
        raise ValueError('Invalid coordinate structure for routing')

    headers = {
        'Authorization': api_key,
        'Content-Type': 'application/json'
    }

    try:
        response = requests.post(
            f"{OPENROUTESERVICE_BASE_URL}/{profile}",
            json=payload,
            headers=headers,
            timeout=20
        )
    except Exception as e:
        logger.error(f"OpenRouteService network error: {str(e)}")
        return None

    if response.status_code == 400:
        message = 'Route request rejected'
        try:
            details = response.json()
            message = details.get('error', {}).get('message', message)
        except Exception:
            pass
        logger.warning(f"OpenRouteService limit hit: {message}")
        raise ValueError(message)

    try:
        response.raise_for_status()
    except Exception as e:
        logger.error(f"OpenRouteService error ({response.status_code}): {str(e)}")
        return None

    try:
        data = response.json()
    except Exception as e:
        logger.error(f"OpenRouteService JSON error: {str(e)}")
        return None

    features = data.get('features', [])
    if not features:
        return None

    feature = features[0]
    props = feature.get('properties', {})
    summary = props.get('summary', {})
    segments = props.get('segments', [])
    steps = segments[0].get('steps', []) if segments else []

    return {
        'geometry': feature.get('geometry'),
        'distance_m': summary.get('distance', 0),
        'duration_s': summary.get('duration', 0),
        'steps': steps
    }


def get_travel_advisories(country_code: str):
    """
    Alias for backward compatibility
    """
    return get_travel_advisory(country_code)
