import copy
import logging
import math
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

TEQUILA_API_KEY = os.getenv("TEQUILA_API_KEY")
TEQUILA_BASE_URL = "https://api.tequila.kiwi.com"

EARTH_RADIUS_KM = 6371.0
DEFAULT_DEPARTURE_OFFSET_DAYS = 30
DEFAULT_FLIGHT_CURRENCY = os.getenv("FLIGHT_CURRENCY", "USD")

TRAIN_CLASS_RATES = {
    "SL": {"label": "Sleeper", "per_km": 0.75, "reservation_fee": 20, "superfast_fee": 45},
    "3A": {"label": "AC 3 Tier", "per_km": 1.9, "reservation_fee": 40, "superfast_fee": 45},
    "2A": {"label": "AC 2 Tier", "per_km": 2.45, "reservation_fee": 50, "superfast_fee": 45},
    "1A": {"label": "AC First", "per_km": 4.35, "reservation_fee": 60, "superfast_fee": 45},
    "CC": {"label": "AC Chair Car", "per_km": 1.28, "reservation_fee": 40, "superfast_fee": 45},
}

CITY_TO_STATION = {
    "delhi": "NDLS",
    "new delhi": "NDLS",
    "mumbai": "CSTM",
    "mumbai csmt": "CSTM",
    "chhatrapati shivaji terminus": "CSTM",
    "bengaluru": "SBC",
    "bangalore": "SBC",
    "chennai": "MAS",
    "kolkata": "HWH",
    "hyderabad": "SC",
    "pune": "PUNE",
    "ahmedabad": "ADI",
    "jaipur": "JP",
    "goa": "MAO",
    "kochi": "ERS",
    "thiruvananthapuram": "TVC",
}

CITY_TO_AIRPORT = {
    "new delhi": "DEL",
    "delhi": "DEL",
    "mumbai": "BOM",
    "bengaluru": "BLR",
    "bangalore": "BLR",
    "chennai": "MAA",
    "kolkata": "CCU",
    "hyderabad": "HYD",
    "pune": "PNQ",
    "goa": "GOI",
    "kochi": "COK",
    "ahmedabad": "AMD",
    "jaipur": "JAI",
    "dubai": "DXB",
    "singapore": "SIN",
    "tokyo": "TYO",
    "osaka": "OSA",
    "paris": "PAR",
    "london": "LON",
    "new york": "NYC",
    "san francisco": "SFO",
    "los angeles": "LAX",
    "sydney": "SYD",
    "melbourne": "MEL",
    "toronto": "YTO",
}

COUNTRY_ALIASES = {
    "INDIA": "IN",
    "UNITED STATES": "US",
    "UNITED STATES OF AMERICA": "US",
}


def _haversine_distance(source: Dict[str, Any], destination: Dict[str, Any]) -> float:
    try:
        lat1 = float(source.get("lat"))
        lon1 = float(source.get("lon"))
        lat2 = float(destination.get("lat"))
        lon2 = float(destination.get("lon"))
    except (TypeError, ValueError):
        return 0.0

    if not all([lat1, lon1, lat2, lon2]):
        return 0.0

    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_KM * c


def _normalize_date(value: Optional[str]) -> datetime:
    if value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    return datetime.utcnow() + timedelta(days=DEFAULT_DEPARTURE_OFFSET_DAYS)


def _estimate_train_quotes(source: Dict[str, Any], destination: Dict[str, Any], passengers: int,
                           departure_date: datetime, distance_km: float) -> List[Dict[str, Any]]:
    if distance_km <= 0:
        distance_km = 800.0

    quotes = []
    passengers = max(1, passengers)

    for class_code, rate_info in TRAIN_CLASS_RATES.items():
        base_fare = distance_km * rate_info["per_km"]
        reservation = rate_info["reservation_fee"]
        superfast = rate_info["superfast_fee"] if distance_km >= 300 else 0
        gst = 0.05 * (base_fare + reservation + superfast)
        per_person = base_fare + reservation + superfast + gst

        quotes.append({
            "id": f"train-{class_code}",
            "mode": "train",
            "provider": "Indian Railways",
            "class": class_code,
            "class_label": rate_info["label"],
            "currency": "INR",
            "price_per_person": round(per_person, 2),
            "group_price": round(per_person * passengers, 2),
            "duration_hours": round(max(6.0, distance_km / 55.0), 1),
            "confidence": "estimated",
            "notes": "Estimation based on IRCTC fare slabs with GST & reservation charges",
            "departure": departure_date.date().isoformat(),
        })

    return quotes


def _resolve_station_code(meta: Dict[str, Any]) -> Optional[str]:
    code = meta.get("station_code") or meta.get("code")
    if code:
        return code.upper()
    name = (meta.get("name") or meta.get("label") or meta.get("display_name") or "").lower()
    return CITY_TO_STATION.get(name)


def _resolve_airport_code(meta: Dict[str, Any]) -> Optional[str]:
    code = meta.get("airport_code") or meta.get("iata")
    if code:
        return code.upper()
    name = (meta.get("name") or meta.get("label") or meta.get("display_name") or "").lower()
    return CITY_TO_AIRPORT.get(name)


def _normalize_country_code(raw_value: Optional[str]) -> str:
    if not raw_value:
        return ""
    code = raw_value.strip().upper()
    if len(code) == 2:
        return code
    return COUNTRY_ALIASES.get(code, code)


def _tequila_headers() -> Dict[str, str]:
    return {"apikey": TEQUILA_API_KEY} if TEQUILA_API_KEY else {}


def _lookup_iata_with_tequila(term: str, country: Optional[str]) -> Optional[str]:
    if not TEQUILA_API_KEY or not term:
        return None
    try:
        params = {
            "term": term,
            "location_types": "city",
            "limit": 1,
        }
        if country:
            params["country"] = country.upper()
        response = requests.get(
            f"{TEQUILA_BASE_URL}/locations/query",
            headers=_tequila_headers(),
            params=params,
            timeout=8,
        )
        response.raise_for_status()
        data = response.json().get("locations", [])
        if data:
            return data[0].get("code")
    except Exception as exc:
        logger.warning("Failed to resolve IATA code via Tequila: %s", exc)
    return None


def _iso_duration_to_hours(duration: Any) -> Optional[float]:
    if isinstance(duration, (int, float)):
        return round(duration / 3600.0, 1)
    if isinstance(duration, str) and duration.startswith("PT"):
        hours = 0.0
        current = duration[2:]
        number = ""
        for char in current:
            if char.isdigit():
                number += char
            else:
                if char == "H" and number:
                    hours += float(number)
                elif char == "M" and number:
                    hours += float(number) / 60.0
                number = ""
        return round(hours, 1)
    return None


def _tequila_flight_quotes(source_code: str, dest_code: str, departure_date: datetime, travelers: int,
                           currency: str) -> List[Dict[str, Any]]:
    if not TEQUILA_API_KEY or not source_code or not dest_code:
        return []

    date_str = departure_date.strftime("%d/%m/%Y")
    params = {
        "fly_from": source_code,
        "fly_to": dest_code,
        "date_from": date_str,
        "date_to": date_str,
        "curr": currency,
        "adults": max(1, travelers),
        "limit": 4,
        "sort": "price",
    }

    try:
        response = requests.get(
            f"{TEQUILA_BASE_URL}/v2/search",
            headers=_tequila_headers(),
            params=params,
            timeout=12,
        )
        response.raise_for_status()
        data = response.json().get("data", [])
    except Exception as exc:
        logger.warning("Flight quote API failed: %s", exc)
        return []

    quotes = []
    for entry in data:
        price = entry.get("price")
        currency_code = entry.get("conversion", {}).get(currency, currency)
        duration_hours = _iso_duration_to_hours(entry.get("duration", {}).get("total"))
        airlines = entry.get("airlines", [])
        carrier = airlines[0] if airlines else "Multiple"

        quotes.append({
            "id": entry.get("id"),
            "mode": "flight",
            "provider": carrier,
            "currency": currency_code,
            "price_per_person": float(price),
            "group_price": round(float(price) * max(1, travelers), 2),
            "duration_hours": duration_hours,
            "stops": entry.get("route") and max(0, len(entry["route"]) - 1),
            "confidence": "live",
            "booking_url": entry.get("deep_link"),
            "departure": entry.get("local_departure", "")[:10],
        })

    return quotes


def _fallback_flight_quotes(distance_km: float, travelers: int, currency: str) -> List[Dict[str, Any]]:
    if distance_km <= 0:
        distance_km = 800

    base_economy = max(120.0, 0.11 * distance_km + 90)
    base_premium = base_economy * 1.6
    base_business = base_economy * 2.4

    tiers = [
        ("Economy", base_economy),
        ("Premium Economy", base_premium),
        ("Business", base_business),
    ]

    quotes = []
    for cabin, price in tiers:
        quotes.append({
            "id": f"flight-{cabin.lower().replace(' ', '-')}",
            "mode": "flight",
            "provider": cabin,
            "currency": currency,
            "price_per_person": round(price, 2),
            "group_price": round(price * max(1, travelers), 2),
            "duration_hours": round(max(3.0, distance_km / 750.0), 1),
            "confidence": "estimated",
            "notes": "Estimated using distance-based heuristic due to missing live API key",
        })

    return quotes


def build_transport_pricing(source_details: Optional[Dict[str, Any]],
                           destination_details: Optional[Dict[str, Any]],
                           departure_date: Optional[str] = None,
                           travelers: int = 1) -> Dict[str, Any]:
    source_details = source_details or {}
    destination_details = destination_details or {}
    travelers = max(1, int(travelers or 1))

    departure = _normalize_date(departure_date)
    distance_km = _haversine_distance(source_details, destination_details)

    source_country = _normalize_country_code(source_details.get("country"))
    destination_country = _normalize_country_code(destination_details.get("country"))

    is_india_trip = source_country == "IN" and destination_country == "IN"

    if is_india_trip:
        quotes = _estimate_train_quotes(source_details, destination_details, travelers, departure, distance_km)
        trip_type = "india_train"
    else:
        source_code = _resolve_airport_code(source_details) or _lookup_iata_with_tequila(source_details.get("name"), source_country)
        dest_code = _resolve_airport_code(destination_details) or _lookup_iata_with_tequila(destination_details.get("name"), destination_country)

        quotes = _tequila_flight_quotes(source_code, dest_code, departure, travelers, DEFAULT_FLIGHT_CURRENCY)
        if not quotes:
            quotes = _fallback_flight_quotes(distance_km, travelers, DEFAULT_FLIGHT_CURRENCY)
        trip_type = "international_flight"

    return {
        "trip_type": trip_type,
        "travelers": travelers,
        "departure_date": departure.date().isoformat(),
        "distance_km": round(distance_km, 1) if distance_km else None,
        "quotes": quotes,
        "source": {
            "label": source_details.get("name") or source_details.get("label"),
            "country": source_country,
        },
        "destination": {
            "label": destination_details.get("name") or destination_details.get("label"),
            "country": destination_country,
        },
    }


def scale_itinerary_for_group(itinerary: Optional[Dict[str, Any]], travelers: int) -> Optional[Dict[str, Any]]:
    if not itinerary or travelers <= 1:
        return itinerary

    data = copy.deepcopy(itinerary)
    multiplier = max(1, travelers)

    for day in data.get("itinerary", []):
        if isinstance(day.get("total_cost"), (int, float)):
            day["total_cost"] = int(round(day.get("total_cost", 0) * multiplier))
        for bucket in ("activities", "meals"):
            for entry in day.get(bucket, []):
                if isinstance(entry.get("cost"), (int, float)):
                    entry["cost"] = int(round(entry.get("cost", 0) * multiplier))

    budget_block = data.get("budget_breakdown")
    if isinstance(budget_block, dict):
        for key, value in budget_block.items():
            if isinstance(value, (int, float)):
                budget_block[key] = int(round(value * multiplier))
            elif isinstance(value, dict):
                for child_key, child_val in value.items():
                    if isinstance(child_val, (int, float)):
                        value[child_key] = int(round(child_val * multiplier))

    data.setdefault("meta", {})
    data["meta"]["group_multiplier"] = multiplier
    return data


def scale_budget_for_group(budget: Optional[Dict[str, Any]], travelers: int) -> Optional[Dict[str, Any]]:
    if not budget or travelers <= 1:
        return budget

    data = copy.deepcopy(budget)
    multiplier = max(1, travelers)

    base_total = data.get("total_budget") or 0
    base_daily = data.get("daily_budget") or 0

    for key in ("total_budget", "daily_budget"):
        if isinstance(data.get(key), (int, float)):
            data[key] = int(round(data[key] * multiplier))

    breakdown = data.get("breakdown")
    if isinstance(breakdown, dict):
        for section in breakdown.values():
            if isinstance(section, dict):
                for sub_key, sub_val in section.items():
                    if isinstance(sub_val, (int, float)):
                        section[sub_key] = int(round(sub_val * multiplier))

    data.setdefault("group_metadata", {})
    data["group_metadata"].update({
        "travelers": multiplier,
        "per_traveler_total": base_total,
        "per_traveler_daily": base_daily,
    })

    return data
