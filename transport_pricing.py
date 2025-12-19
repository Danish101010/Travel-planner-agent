import copy
import logging
import math
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

EARTH_RADIUS_KM = 6371.0
DEFAULT_DEPARTURE_OFFSET_DAYS = 30
DEFAULT_FLIGHT_CURRENCY = os.getenv("FLIGHT_CURRENCY", "USD")
QUOTE_CACHE_TTL_SECONDS = int(os.getenv("TRANSPORT_QUOTE_CACHE_TTL", "21600"))  # default 6h
TRAVELPAYOUTS_TOKEN = os.getenv("TRAVELPAYOUTS_TOKEN")
TRAVELPAYOUTS_SEARCH_URL = "https://api.travelpayouts.com/v2/prices/latest"

_default_irctc_host = "irctc1.p.rapidapi.com"
_raw_irctc_host = os.getenv("IRCTC_RAPIDAPI_HOST", _default_irctc_host) or _default_irctc_host
if _raw_irctc_host.startswith("http"):
    _parsed_irctc_host = _raw_irctc_host.replace("https://", "").replace("http://", "").strip("/")
else:
    _parsed_irctc_host = _raw_irctc_host.strip("/")
if not _parsed_irctc_host or "irctc" not in _parsed_irctc_host.lower():
    _parsed_irctc_host = _default_irctc_host
IRCTC_RAPIDAPI_HOST = _parsed_irctc_host
IRCTC_BASE_URL = f"https://{IRCTC_RAPIDAPI_HOST}/api/v3/trainBetweenStations"
IRCTC_STATION_SEARCH_URL = f"https://{IRCTC_RAPIDAPI_HOST}/api/v1/searchStation"
IRCTC_RAPIDAPI_KEY = os.getenv("IRCTC_RAPIDAPI_KEY") or os.getenv("RAPIDAPI_KEY")

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

_quote_cache: Dict[str, Dict[str, Dict[str, Any]]] = {
    "irctc": {},
    "travelpayouts": {},
}

_station_cache: Dict[str, Optional[str]] = {}


def _cached_quotes(channel: str, key: str):
    bucket = _quote_cache.get(channel, {})
    entry = bucket.get(key)
    if not entry:
        return None
    if time.time() - entry["ts"] > QUOTE_CACHE_TTL_SECONDS:
        bucket.pop(key, None)
        return None
    return copy.deepcopy(entry["data"])


def _store_cached_quotes(channel: str, key: str, data):
    if channel not in _quote_cache:
        _quote_cache[channel] = {}
    _quote_cache[channel][key] = {
        "data": copy.deepcopy(data),
        "ts": time.time(),
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


def _flatten_irctc_fares(fare_blob: Any) -> Dict[str, float]:
    fares: Dict[str, float] = {}
    if isinstance(fare_blob, dict):
        for key, value in fare_blob.items():
            if isinstance(value, (int, float, str)):
                try:
                    fares[key.upper()] = float(value)
                except (TypeError, ValueError):
                    continue
            elif isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    if sub_value is None:
                        continue
                    try:
                        fares[sub_key.upper()] = float(sub_value)
                    except (TypeError, ValueError):
                        continue
    elif isinstance(fare_blob, list):
        for entry in fare_blob:
            if not isinstance(entry, dict):
                continue
            class_code = (entry.get("classType") or entry.get("class_code") or entry.get("class") or entry.get("code") or "").strip()
            if not class_code:
                continue
            raw_amount = entry.get("fare") or entry.get("avg_fare") or entry.get("price") or entry.get("value")
            if raw_amount is None:
                continue
            try:
                fares[class_code.upper()] = float(raw_amount)
            except (TypeError, ValueError):
                continue
    return fares


def _irctc_train_quotes(source_code: Optional[str], dest_code: Optional[str], departure_date: datetime,
                        passengers: int) -> List[Dict[str, Any]]:
    if not IRCTC_RAPIDAPI_KEY:
        logger.info("Skipping IRCTC lookup: IRCTC_RAPIDAPI_KEY missing")
        return []
    if not source_code or not dest_code:
        logger.info("Skipping IRCTC lookup: station codes unresolved (%s -> %s)", source_code, dest_code)
        return []

    cache_key = f"{source_code}:{dest_code}:{departure_date.date().isoformat()}"
    cached = _cached_quotes("irctc", cache_key)
    if cached is not None:
        logger.info("IRCTC cache hit for %s", cache_key)
        return cached

    logger.info(
        "IRCTC lookup %s -> %s (%s)",
        source_code,
        dest_code,
        departure_date.date().isoformat(),
    )

    params = {
        "fromStationCode": source_code.upper(),
        "toStationCode": dest_code.upper(),
        "dateOfJourney": departure_date.strftime("%Y-%m-%d"),
    }
    headers = {
        "X-RapidAPI-Key": IRCTC_RAPIDAPI_KEY,
        "X-RapidAPI-Host": IRCTC_RAPIDAPI_HOST,
    }

    try:
        response = requests.get(
            IRCTC_BASE_URL,
            headers=headers,
            params=params,
            timeout=12,
        )
        response.raise_for_status()
        payload = response.json() or {}
    except Exception as exc:
        logger.warning("IRCTC train quote lookup failed for %s -> %s (%s): %s",
                       source_code, dest_code, departure_date.date().isoformat(), exc)
        return []

    trains = payload.get("data") or payload.get("train") or []
    if isinstance(trains, dict):
        trains = list(trains.values())

    quotes: List[Dict[str, Any]] = []
    passengers = max(1, passengers)

    for train in trains:
        if not isinstance(train, dict):
            continue
        fare_table = _flatten_irctc_fares(train.get("fare") or train.get("classes") or {})
        if not fare_table:
            continue

        duration_hours = _iso_duration_to_hours(train.get("duration") or train.get("duration_hr"))
        distance = train.get("distance_km") or train.get("distance")
        provider = train.get("train_name") or train.get("trainName") or "Indian Railways"
        train_id = train.get("train_number") or train.get("trainNo") or provider

        for class_code, amount in fare_table.items():
            if amount <= 0:
                continue
            per_person = round(amount, 2)
            quotes.append({
                "id": f"{train_id}-{class_code}",
                "mode": "train",
                "provider": provider,
                "class": class_code,
                "currency": "INR",
                "price_per_person": per_person,
                "group_price": round(per_person * passengers, 2),
                "duration_hours": duration_hours,
                "confidence": "live",
                "notes": "Fare sourced from IRCTC (RapidAPI free tier)",
                "departure": departure_date.date().isoformat(),
                "distance_km": distance,
            })
            if len(quotes) >= 6:
                break
        if len(quotes) >= 6:
            break

    if quotes:
        logger.info("IRCTC returned %s live quotes for %s", len(quotes), cache_key)
        _store_cached_quotes("irctc", cache_key, quotes)

    return quotes


def _resolve_station_code(meta: Dict[str, Any]) -> Optional[str]:
    code = meta.get("station_code") or meta.get("code")
    if code:
        return code.upper()
    name = (meta.get("name") or meta.get("label") or meta.get("display_name") or "").lower()
    if not name:
        return None

    cached = _station_cache.get(name)
    if cached is not None:
        return cached

    mapped = CITY_TO_STATION.get(name)
    if mapped:
        _station_cache[name] = mapped
        return mapped

    remote_code = _lookup_station_code_remote(name)
    if remote_code:
        _station_cache[name] = remote_code
        return remote_code

    _station_cache[name] = None
    return None


def _lookup_station_code_remote(query: str) -> Optional[str]:
    if not IRCTC_RAPIDAPI_KEY:
        logger.info("Station lookup skipped: IRCTC_RAPIDAPI_KEY missing")
        return None
    if not query or len(query) < 3:
        return None

    headers = {
        "X-RapidAPI-Key": IRCTC_RAPIDAPI_KEY,
        "X-RapidAPI-Host": IRCTC_RAPIDAPI_HOST,
    }
    params = {"query": query}

    try:
        response = requests.get(
            IRCTC_STATION_SEARCH_URL,
            headers=headers,
            params=params,
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json() or {}
    except Exception as exc:
        logger.warning("Station lookup failed for %s: %s", query, exc)
        return None

    entries = payload.get("data") or []
    if isinstance(entries, dict):
        entries = list(entries.values())

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        code = entry.get("station_code") or entry.get("stationCode") or entry.get("code")
        name = entry.get("station_name") or entry.get("stationName") or entry.get("name")
        if code and name:
            logger.info("Station lookup success: %s -> %s", query, code)
            return code.upper()

    return None


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


def _iso_duration_to_hours(duration: Any) -> Optional[float]:
    if isinstance(duration, (int, float)):
        return round(duration / 3600.0, 1)
    if isinstance(duration, str):
        value = duration.strip()
        if value.startswith("PT"):
            hours = 0.0
            current = value[2:]
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
        if ":" in value:
            try:
                parts = [float(part) for part in value.split(":") if part.strip()]
            except ValueError:
                parts = []
            if parts:
                hours = parts[0]
                if len(parts) > 1:
                    hours += parts[1] / 60.0
                if len(parts) > 2:
                    hours += parts[2] / 3600.0
                return round(hours, 1)
    return None


def _travelpayouts_flight_quotes(source_code: Optional[str], dest_code: Optional[str],
                                 departure_date: datetime, travelers: int,
                                 currency: str) -> List[Dict[str, Any]]:
    if not TRAVELPAYOUTS_TOKEN or not source_code or not dest_code:
        return []
    if source_code.upper() == dest_code.upper():
        return []

    cache_key = f"{source_code}:{dest_code}:{departure_date.date().isoformat()}:{currency}:{travelers}"
    cached = _cached_quotes("travelpayouts", cache_key)
    if cached is not None:
        logger.info("TravelPayouts cache hit for %s", cache_key)
        return cached

    logger.info(
        "TravelPayouts lookup %s -> %s (%s, %s pax)",
        source_code,
        dest_code,
        departure_date.date().isoformat(),
        travelers,
    )

    params = {
        "origin": source_code.upper(),
        "destination": dest_code.upper(),
        "currency": currency,
        "limit": 5,
        "page": 1,
        "depart_date": departure_date.strftime("%Y-%m-%d"),
        "show_to_affiliates": "true",
        "sorting": "price",
        "token": TRAVELPAYOUTS_TOKEN,
    }
    headers = {
        "X-Access-Token": TRAVELPAYOUTS_TOKEN,
    }

    def _perform_request(request_params):
        try:
            response = requests.get(
                TRAVELPAYOUTS_SEARCH_URL,
                params=request_params,
                headers=headers,
                timeout=12,
            )
            response.raise_for_status()
            payload = response.json() or {}
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", "unknown")
            logger.warning(
                "TravelPayouts API HTTP %s for %s -> %s",
                status,
                request_params.get("origin"),
                request_params.get("destination"),
            )
            return None

        error_message = payload.get("error") or payload.get("message")
        if error_message:
            logger.warning("TravelPayouts API response error: %s", error_message)
        if payload.get("success") is False and not error_message:
            logger.warning("TravelPayouts marked request unsuccessful for %s -> %s",
                           request_params.get("origin"), request_params.get("destination"))
        return payload

    def _extract_entries(payload_obj):
        if not isinstance(payload_obj, dict):
            return []
        entries_obj = payload_obj.get("data") or payload_obj.get("results") or []
        if isinstance(entries_obj, dict):
            entries_list = list(entries_obj.values())
        else:
            entries_list = entries_obj if isinstance(entries_obj, list) else []
        return entries_list

    payload = _perform_request(params)
    entries = _extract_entries(payload)

    if not entries:
        logger.info("TravelPayouts returned no fares for %s; retrying without depart_date filter", cache_key)
        retry_params = dict(params)
        retry_params.pop("depart_date", None)
        payload = _perform_request(retry_params)
        entries = _extract_entries(payload)
        if not entries:
            logger.info("TravelPayouts still returned no fares for %s after retry", cache_key)

    quotes: List[Dict[str, Any]] = []
    travelers = max(1, travelers)

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        price = entry.get("value") or entry.get("price")
        if not price:
            continue
        try:
            per_person = float(price)
        except (TypeError, ValueError):
            continue

        flight_duration = entry.get("duration") or entry.get("duration_to") or entry.get("duration_from")
        duration_hours = _iso_duration_to_hours(flight_duration)

        quote_id = entry.get("id") or f"tp-{entry.get('airline')}-{entry.get('flight_number')}-{entry.get('departure_at')}"
        provider = entry.get("airline") or "TravelPayouts"
        departure = (entry.get("departure_at") or entry.get("depart_date") or "")[:10]

        quotes.append({
            "id": quote_id,
            "mode": "flight",
            "provider": provider,
            "currency": currency,
            "price_per_person": round(per_person, 2),
            "group_price": round(per_person * travelers, 2),
            "duration_hours": duration_hours,
            "stops": entry.get("number_of_changes"),
            "confidence": "live",
            "booking_url": entry.get("link"),
            "departure": departure,
            "notes": "TravelPayouts fare cache (free tier)",
        })

        if len(quotes) >= 4:
            break

    if quotes:
        logger.info("TravelPayouts returned %s live quotes for %s", len(quotes), cache_key)
        _store_cached_quotes("travelpayouts", cache_key, quotes)

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
        logger.info(
            "Domestic India trip detected (%s -> %s)",
            source_details.get("name"),
            destination_details.get("name"),
        )
        source_station = _resolve_station_code(source_details)
        dest_station = _resolve_station_code(destination_details)
        logger.info("Resolved station codes: %s -> %s", source_station, dest_station)
        quotes = _irctc_train_quotes(source_station, dest_station, departure, travelers)
        if not quotes:
            logger.info("Using heuristic train fares due to missing live IRCTC data")
            quotes = _estimate_train_quotes(source_details, destination_details, travelers, departure, distance_km)
        trip_type = "india_train"
    else:
        logger.info(
            "International/mixed trip (%s -> %s): activating flight pricing",
            source_details.get("name"),
            destination_details.get("name"),
        )
        source_code = _resolve_airport_code(source_details)
        dest_code = _resolve_airport_code(destination_details)
        logger.info("Resolved airport codes: %s -> %s", source_code, dest_code)

        quotes: List[Dict[str, Any]] = []
        quotes = _travelpayouts_flight_quotes(source_code, dest_code, departure, travelers, DEFAULT_FLIGHT_CURRENCY)
        if not quotes:
            logger.info("Using heuristic flight fares due to missing live quotes")
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
