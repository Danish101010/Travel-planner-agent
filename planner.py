from google import genai
import json
import os
import time
import re
from typing import Any, Dict, List, Optional, Tuple

client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
MODEL_NAME = "gemini-3.1-flash-lite"


def _parse_json_safe(text: str):
    """Attempt to parse potentially noisy JSON from model output."""
    if not text:
        raise ValueError("Empty model response")

    # Remove code fences if present
    if text.startswith("```"):
        text = text.replace("```json", "").replace("```", "").strip()

    # First attempt
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try slicing from first { to last }
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        sliced = text[start:end]
        try:
            return json.loads(sliced)
        except json.JSONDecodeError:
            text = sliced

    # Remove trailing commas before } or ]
    cleaned = re.sub(r",\s*([}\]])", r"\1", text)
    
    # Remove duplicate commas
    cleaned = re.sub(r",\s*,", ",", cleaned)
    
    # Fix ALL number ranges (e.g., "3500 - 4500" or "6-8") -> use midpoint
    # Handles ranges in any numeric context
    def replace_range_with_midpoint(match):
        try:
            num_str = match.group(0)
            # Extract numbers from patterns like "3500 - 4500" or "6-8"
            numbers = re.findall(r'\d+', num_str)
            if len(numbers) >= 2:
                avg = sum(int(n) for n in numbers[:2]) // 2
                return str(avg)
        except:
            pass
        return match.group(0)
    
    # Replace all numeric ranges with their midpoint
    cleaned = re.sub(r'\d+\s*-\s*\d+', replace_range_with_midpoint, cleaned)
    
    # Remove unescaped newlines inside string values
    cleaned = re.sub(r':\s*"([^"]*)\n([^"]*)"', lambda m: f': "{m.group(1)} {m.group(2)}"', cleaned)
    
    # Try to parse cleaned version
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        # Log snippet around error for debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"JSON parse failed at char {e.pos}: {cleaned[max(0, e.pos-50):e.pos+50]}")
        raise


ITINERARY_PROMPT = """
You are an expert travel planner creating a comprehensive day-by-day itinerary.

INPUT:
- Source (departure city): {source}
- Destination: {destination}
- Days: {days}
- Total Budget: {budget} {source_currency}
- Budget Constraints: {budget_breakdown}
- Travel Style: {style}
- Interests: {interests}
- Group: {group}
- Travelers: {travelers}
- Special Needs: {special_needs}

Create a detailed JSON itinerary with:
- Day-by-day breakdown (morning, afternoon, evening)
- Specific times for activities
- Estimated costs per activity
- Transportation between locations
- Restaurant recommendations with cuisine type
- Attractions with brief descriptions
- Local tips and warnings
- Budget breakdown

RULES:
- Output ONLY valid JSON
- No markdown, no explanation
- CRITICAL: You MUST strictly adhere to the {budget_breakdown} constraints. Do not exceed the allocated budget for food or activities.
- Include realistic activity times
- Add backup options for rainy days
- Consider travel time between locations.
- CRITICAL: For EVERY activity, you MUST specify the exact transport method (e.g., '15m subway via Marunouchi Line', '10m walk') to the next location in the 'transit_to_next' field. Do not omit this field.
- ALWAYS calculate costs for the entire group of {travelers} travelers (not per person)
- CRITICAL: All generated costs and budgets MUST be natively estimated and returned in the {source_currency} currency. Do not use USD unless the source currency is USD.
- CRITICAL: Use ONLY single integer values for all numeric fields (never ranges like "6-8" or "3500 - 4500")
- CRITICAL: All numbers must be valid JSON integers (e.g., 3500, not "3500 - 4500")
- Ensure all string values are properly closed and contain no unescaped newlines

Format:
{{
  "budget_breakdown": {{"accommodation": 0, "food": 0, "activities": 0, "transport": 0}},
  "itinerary": [
    {{
      "day": 1,
      "date": "Day 1",
      "theme": "...",
      "activities": [
        {{
          "time": "09:00",
          "activity": "...",
          "location": "...",
          "cost": 0,
          "duration_minutes": 60,
          "description": "...",
          "tip": "...",
          "transit_to_next": "..."
        }}
      ],
      "meals": [
        {{
          "time": "12:00",
          "type": "lunch",
          "restaurant": "...",
          "cuisine": "...",
          "cost": 0,
          "specialty": "..."
        }}
      ],
      "total_cost": 0
    }}
  ],
  "recommendations": {{
    "best_time_to_visit": "...",
    "local_warnings": [...],
    "money_saving_tips": [...],
    "hidden_gems": [...]
  }}
}}
"""

BUDGET_PROMPT = """
You are a travel budget expert. Create a detailed budget breakdown for this trip.

Destination: {destination}
Days: {days}
Budget: {budget} {source_currency}
Travel Style: {style}
Source (departure city): {source}
Travelers: {travelers}

Output ONLY valid JSON with:
- Daily budget limits
- Cost per category (accommodation, food, activities, transport)
- Money saving tips specific to this destination
- Estimated total with breakdown
- Include per-person notes wherever relevant, but make sure totals reflect all {travelers} travelers
- CRITICAL: All generated costs and budgets MUST be natively estimated and returned in the {source_currency} currency. Do not use USD unless the source currency is USD.
- CRITICAL: Use ONLY single integer values (never ranges like "3500 - 4500", use exact numbers like 3800)

Format:
{{
  "total_budget": 0,
  "daily_budget": 0,
  "breakdown": {{
    "accommodation": {{"per_night": 0, "nights": {days}, "subtotal": 0}},
    "food": {{"per_day": 0, "days": {days}, "subtotal": 0}},
    "activities": {{"estimated": 0}},
    "transport": {{"estimated": 0}},
    "contingency": {{"percent": 10, "amount": 0}}
  }},
  "savings_tips": [...]
}}
"""

MEAL_WINDOWS = (
    {'type': 'breakfast', 'label': 'Breakfast', 'start': 6 * 60 + 30, 'end': 10 * 60},
    {'type': 'lunch', 'label': 'Lunch', 'start': 11 * 60 + 30, 'end': 14 * 60 + 30},
    {'type': 'snack', 'label': 'Snacks', 'start': 15 * 60, 'end': 17 * 60 + 30},
    {'type': 'dinner', 'label': 'Dinner', 'start': 18 * 60, 'end': 21 * 60 + 30},
)

TRAVEL_ACTIVITY_KEYWORDS = (
    'travel', 'transfer', 'transit', 'journey', 'drive', 'flight', 'train', 'depart',
    'arrival', 'commute', 'ferry', 'bus'
)

MAX_SCHEDULED_MEALS = 3
MIN_DAY_SPAN_MINUTES = 14 * 60


def planner_agent(destination: str, days: int, budget: float, style: str,
                  interests: list, group: str, special_needs: str, source: str,
                  travelers: int = 1, source_currency: str = "USD", budget_breakdown: str = "None"):
    """Generate comprehensive travel itinerary"""
    
    prompt = ITINERARY_PROMPT.format(
        source=source,
        destination=destination,
        days=days,
        budget=budget,
        budget_breakdown=budget_breakdown,
        source_currency=source_currency,
        style=style,
        interests=", ".join(interests),
        group=group,
        special_needs=special_needs or "None",
        travelers=max(1, travelers)
    )

    max_retries = 3
    for attempt in range(max_retries):
        try:
          response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
          text = (response.text or "").strip()
          return _parse_json_safe(text)
        except Exception as e:
            if ("429" in str(e) or "503" in str(e)) and attempt < max_retries - 1:
                wait_time = 15 * (attempt + 1)
                print(f"API busy ({e}). Waiting {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                raise


def budget_agent(destination: str, days: int, budget: float, style: str, source: str,
                 travelers: int = 1, source_currency: str = "USD"):
    """Generate detailed budget breakdown"""
    
    prompt = BUDGET_PROMPT.format(
        destination=destination,
        days=days,
        budget=budget,
        source_currency=source_currency,
        style=style,
        source=source,
        travelers=max(1, travelers)
    )

    max_retries = 3
    for attempt in range(max_retries):
        try:
          response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
          text = (response.text or "").strip()
          return _parse_json_safe(text)
        except Exception as e:
            if ("429" in str(e) or "503" in str(e)) and attempt < max_retries - 1:
                wait_time = 15 * (attempt + 1)
                print(f"API busy ({e}). Waiting {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                raise

ROUTING_PROMPT = """
You are a logistics travel routing expert. The user is traveling from {source} to {destination}. 
Analyze the geographic locations. Determine if direct transport (flight/train) is likely, or if multi-modal transport is required (e.g., taking a train or bus from a smaller town to the nearest major commercial airport, then catching a flight).

Output a brief, generalized strategic recommendation. Do NOT recommend specific booked tickets or exact flight numbers.
Output ONLY valid JSON in this exact format:
{{
  "strategy": "Your brief 1-2 sentence routing recommendation here."
}}
"""

def routing_agent(source: str, destination: str):
    """Generate high-level routing strategy"""
    prompt = ROUTING_PROMPT.format(source=source, destination=destination)
    
    max_retries = 2
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
            text = (response.text or "").strip()
            return _parse_json_safe(text)
        except Exception as e:
            if ("429" in str(e) or "503" in str(e)) and attempt < max_retries - 1:
                time.sleep(5)
            else:
                return {"strategy": ""}
    return {"strategy": ""}

def _coerce_cost(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def normalize_itinerary_costs(itinerary: Dict[str, Any], total_budget: float, days: int) -> Dict[str, Any]:
    """Ensure costs are valid integers and compute day totals. No artificial scaling down."""
    if not itinerary or not isinstance(itinerary, dict):
        return itinerary

    schedule: List[Dict[str, Any]] = itinerary.get('itinerary') or []
    if not isinstance(schedule, list) or not schedule:
        return itinerary

    for day in schedule:
        if not isinstance(day, dict):
            continue
        day_total = 0
        for bucket_name in ('activities', 'meals'):
            bucket = day.get(bucket_name) or []
            if not isinstance(bucket, list):
                continue
            for entry in bucket:
                if not isinstance(entry, dict):
                    continue
                cost = _coerce_cost(entry.get('cost'))
                entry['cost'] = cost
                day_total += cost

        day['total_cost'] = int(day_total)

    return itinerary


def normalize_budget_estimate(budget_data: Dict[str, Any], total_budget: float, days: int) -> Dict[str, Any]:
    """Ensure budget breakdown contains valid numbers without artificial scaling."""
    if not budget_data or not isinstance(budget_data, dict):
        return budget_data

    budget_data['total_budget'] = _coerce_cost(budget_data.get('total_budget'))
    budget_data['daily_budget'] = _coerce_cost(budget_data.get('daily_budget'))

    breakdown = budget_data.get('breakdown')
    if not isinstance(breakdown, dict):
        return budget_data

    for key, section in breakdown.items():
        if not isinstance(section, dict):
            continue
            
        if 'subtotal' in section:
            section['subtotal'] = _coerce_cost(section['subtotal'])
        if 'estimated' in section:
            section['estimated'] = _coerce_cost(section['estimated'])
        if 'amount' in section:
            section['amount'] = _coerce_cost(section['amount'])
        if 'per_night' in section:
            section['per_night'] = _coerce_cost(section['per_night'])
        if 'per_day' in section:
            section['per_day'] = _coerce_cost(section['per_day'])

    return budget_data


def _parse_minutes(value: Any) -> Optional[int]:
    if isinstance(value, str):
        text = value.strip().lower()
        match = re.match(r'^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', text)
        if match:
            hour = int(match.group(1)) % 24
            minute = int(match.group(2) or 0)
            meridian = match.group(3)
            if meridian == 'pm' and hour != 12:
                hour += 12
            if meridian == 'am' and hour == 12:
                hour = 0
            return hour * 60 + minute
    return None


def _format_minutes(total_minutes: int) -> str:
    total_minutes = max(0, min(total_minutes, 23 * 60 + 59))
    hour = total_minutes // 60
    minute = total_minutes % 60
    return f"{hour:02d}:{minute:02d}"


def _clamp_minutes(value: int, min_value: int, max_value: int) -> int:
    return max(min_value, min(value, max_value))


def _is_travel_entry(entry: Dict[str, Any]) -> bool:
    blob = ' '.join([
        str(entry.get('activity', '')),
        str(entry.get('description', '')),
        str(entry.get('tip', ''))
    ]).lower()
    return any(keyword in blob for keyword in TRAVEL_ACTIVITY_KEYWORDS)


def _activity_range(entry: Dict[str, Any]) -> Optional[Tuple[int, int]]:
    start = _parse_minutes(entry.get('time'))
    if start is None:
        return None
    try:
        duration = int(entry.get('duration_minutes') or 60)
    except (TypeError, ValueError):
        duration = 60
    duration = max(30, min(duration, 6 * 60))
    return start, start + duration


def _window_overlaps_travel(window: Dict[str, int], activities: List[Dict[str, Any]]) -> bool:
    for entry in activities:
        if not isinstance(entry, dict) or not _is_travel_entry(entry):
            continue
        span = _activity_range(entry)
        if not span:
            continue
        start, end = span
        if end >= window['start'] and start <= window['end']:
            return True
    return False


def _infer_day_window(activities: List[Dict[str, Any]]) -> Tuple[int, int]:
    times = []
    for entry in activities:
        if not isinstance(entry, dict):
            continue
        minute_value = _parse_minutes(entry.get('time'))
        if minute_value is not None:
            times.append(minute_value)
    if not times:
        return 8 * 60, 22 * 60
    start = min(times)
    end = max(times)
    if end - start < MIN_DAY_SPAN_MINUTES:
        end = start + MIN_DAY_SPAN_MINUTES
    return start, min(end, 23 * 60 + 50)


def schedule_meals(day_activities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(day_activities, list):
        return []

    day_start, day_end = _infer_day_window(day_activities)
    scheduled = []

    for window in MEAL_WINDOWS:
        if len(scheduled) >= MAX_SCHEDULED_MEALS:
            break
        if window['end'] < day_start - 60 or window['start'] > day_end + 60:
            continue
        if _window_overlaps_travel(window, day_activities):
            continue
        midpoint = int((window['start'] + window['end']) / 2)
        scheduled.append({
            'type': window['type'],
            'label': window['label'],
            'time': _format_minutes(_clamp_minutes(midpoint, day_start, day_end)),
            'window': (window['start'], window['end'])
        })

    if not scheduled and day_activities:
        midpoint = int((day_start + day_end) / 2)
        scheduled.append({
            'type': 'snack',
            'label': 'Snacks',
            'time': _format_minutes(midpoint),
            'window': (midpoint - 30, midpoint + 30)
        })

    return scheduled[:MAX_SCHEDULED_MEALS]


def _estimate_meal_cost(meal_type: str) -> int:
    defaults = {
        'breakfast': 12,
        'lunch': 18,
        'dinner': 24,
        'snack': 10
    }
    return defaults.get((meal_type or '').lower(), 15)


def _extract_cuisine_from_poi(poi: Dict[str, Any]) -> str:
    kinds = poi.get('kinds') or []
    if isinstance(kinds, str):
        kinds = kinds.split(',')
    cuisines = []
    for kind in kinds:
        if not kind:
            continue
        if any(token in kind for token in ('food', 'cafe', 'restaurant', 'cuisine')):
            cuisines.append(kind.replace('_', ' ').title())
    return ', '.join(dict.fromkeys(cuisines)) or 'Local cuisine'


def _recompute_day_totals(itinerary: Dict[str, Any]) -> None:
    schedule = itinerary.get('itinerary') if isinstance(itinerary, dict) else []
    if not isinstance(schedule, list):
        return
    for day in schedule:
        if not isinstance(day, dict):
            continue
        total = 0
        for bucket in ('activities', 'meals'):
            for entry in day.get(bucket, []) or []:
                if isinstance(entry, dict):
                    total += _coerce_cost(entry.get('cost'))
        day['total_cost'] = total


def apply_meal_pois(itinerary: Dict[str, Any], meal_pois: List[Dict[str, Any]],
                    fallback_source: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not itinerary or not isinstance(itinerary, dict) or not meal_pois:
        return itinerary

    schedule = itinerary.get('itinerary')
    if not isinstance(schedule, list):
        return itinerary

    fallback_lookup = {}
    if isinstance(fallback_source, dict):
        for day in fallback_source.get('itinerary', []) or []:
            if isinstance(day, dict):
                fallback_lookup[day.get('day')] = day.get('meals', [])

    ordered_pois = [poi for poi in meal_pois if isinstance(poi, dict)]
    if len(ordered_pois) < 6:
        # If Geoapify found very few restaurants, do not inject them to prevent heavy repetition across days.
        return itinerary

    poi_index = 0
    total_pois = len(ordered_pois)

    for day in schedule:
        if not isinstance(day, dict):
            continue
        slots = schedule_meals(day.get('activities') or [])
        if not slots:
            continue
        fallback_meals = fallback_lookup.get(day.get('day')) or day.get('meals') or []
        curated = []
        for slot_idx, slot in enumerate(slots):
            poi = ordered_pois[poi_index % total_pois]
            poi_index += 1
            fallback_entry = fallback_meals[slot_idx] if slot_idx < len(fallback_meals) else {}
            cost = _coerce_cost(fallback_entry.get('cost')) if isinstance(fallback_entry, dict) else 0
            if cost <= 0:
                cost = _estimate_meal_cost(slot['type'])
            specialty = ''
            if isinstance(fallback_entry, dict):
                specialty = fallback_entry.get('specialty') or ''
            if not specialty:
                specialty = poi.get('description') or 'Local favorite'

            curated.append({
                'time': slot['time'],
                'type': slot['label'],
                'restaurant': poi.get('name', 'Local Favorite'),
                'cuisine': _extract_cuisine_from_poi(poi),
                'cost': cost,
                'specialty': specialty,
                'address': poi.get('address', ''),
                'source_url': poi.get('url')
            })

        if curated:
            day['meals'] = curated
            day.setdefault('meta', {})['meal_source'] = 'geoapify'

    _recompute_day_totals(itinerary)
    return itinerary
