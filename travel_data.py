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

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

# Free APIs (no keys required)
OPEN_METEO_URL = "https://api.open-meteo.com/v1"
GEONAMES_TIMEZONE_URL = "http://api.geonames.org/timezoneJSON"
GEONAMES_USERNAME = "demo"  # Free tier username
RESTCOUNTRIES_URL = "https://restcountries.com/v3.1"
TRAVEL_ADVISORY_URL = "https://www.travel-advisory.info/api"
EXCHANGERATE_URL = "https://api.exchangerate-api.com/v4/latest"


@lru_cache(maxsize=100)
def autocomplete_destination(query: str, limit: int = 10):
    """
    Autocomplete destinations using fallback hardcoded major cities.
    Free tier, no API key needed. Instant response from cache.
    """
    if not query or len(query) < 2:
        return []
    
    # Use fallback cities directly (most reliable, instant)
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
    """
    Get country information using RestCountries API (completely free).
    Returns capital, currency, languages, etc.
    """
    try:
        response = requests.get(
            f"{RESTCOUNTRIES_URL}/name/{country_name}",
            params={'fullText': 'false'},
            timeout=10
        )
        response.raise_for_status()
        countries = response.json()
        
        if countries and len(countries) > 0:
            country = countries[0]
            currencies = country.get('currencies', {})
            currency_code = list(currencies.keys())[0] if currencies else 'USD'
            currency_info = currencies.get(currency_code, {})
            
            return {
                'name': country.get('name', {}).get('common', country_name),
                'capital': country.get('capital', ['N/A'])[0] if country.get('capital') else 'N/A',
                'region': country.get('region', 'N/A'),
                'subregion': country.get('subregion', 'N/A'),
                'population': country.get('population', 0),
                'area': country.get('area', 0),
                'currency_code': currency_code,
                'currency_name': currency_info.get('name', 'Unknown'),
                'currency_symbol': currency_info.get('symbol', ''),
                'languages': list(country.get('languages', {}).values()),
                'country_code': country.get('cca2', ''),
                'timezones': country.get('timezones', []),
                'flag': country.get('flags', {}).get('png', ''),
            }
        return None
    except Exception as e:
        logger.error(f"Country info error for '{country_name}': {str(e)}")
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


def get_travel_advisories(country_code: str):
    """
    Alias for backward compatibility
    """
    return get_travel_advisory(country_code)
