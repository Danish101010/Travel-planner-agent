import google.generativeai as genai
import json
import os
import time
import re
from typing import Any, Dict, List, Optional, Tuple

genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# Keep the requested model; do not force JSON mode (unsupported on this model)
MODEL = genai.GenerativeModel("gemma-3-4b-it")


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
- Budget: ${budget}
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
- Stay within budget
- Include realistic activity times
- Add backup options for rainy days
- Consider travel time between locations
- ALWAYS calculate costs for the entire group of {travelers} travelers (not per person)
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
          "tip": "..."
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
Budget: ${budget}
Travel Style: {style}
Source (departure city): {source}
Travelers: {travelers}

Output ONLY valid JSON with:
- Daily budget limits
- Cost per category (accommodation, food, activities, transport)
- Money saving tips specific to this destination
- Estimated total with breakdown
- Include per-person notes wherever relevant, but make sure totals reflect all {travelers} travelers
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
                  travelers: int = 1):
    """Generate comprehensive travel itinerary"""
    
    prompt = ITINERARY_PROMPT.format(
        source=source,
        destination=destination,
        days=days,
        budget=budget,
        style=style,
        interests=", ".join(interests),
        group=group,
        special_needs=special_needs or "None",
        travelers=max(1, travelers)
    )

    max_retries = 3
    for attempt in range(max_retries):
        try:
          response = MODEL.generate_content(prompt)
          text = (response.text or "").strip()
          return _parse_json_safe(text)
        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:
                wait_time = 15 * (attempt + 1)
                print(f"Rate limit hit. Waiting {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                raise


def budget_agent(destination: str, days: int, budget: float, style: str, source: str,
                 travelers: int = 1):
    """Generate detailed budget breakdown"""
    
    prompt = BUDGET_PROMPT.format(
        destination=destination,
        days=days,
        budget=budget,
        style=style,
        source=source,
        travelers=max(1, travelers)
    )

    max_retries = 3
    for attempt in range(max_retries):
        try:
          response = MODEL.generate_content(prompt)
          text = (response.text or "").strip()
          return _parse_json_safe(text)
        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:
                wait_time = 15 * (attempt + 1)
                print(f"Rate limit hit. Waiting {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                raise

def _coerce_cost(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def normalize_itinerary_costs(itinerary: Dict[str, Any], total_budget: float, days: int) -> Dict[str, Any]:
    """Clamp per-activity and per-day costs so they cannot explode beyond user budget."""
    if not itinerary or not isinstance(itinerary, dict):
        return itinerary

    schedule: List[Dict[str, Any]] = itinerary.get('itinerary') or []
    if not isinstance(schedule, list) or not schedule:
        return itinerary

    days = max(1, int(days or 1))
    safe_budget = max(100.0, float(total_budget or 100.0))
    per_day_base = safe_budget / days
    per_day_cap = max(60.0, per_day_base * 1.2)
    per_entry_cap = max(10.0, min(per_day_cap * 0.5, per_day_base * 0.35, 95.0))

    for day in schedule:
        if not isinstance(day, dict):
            continue
        bucket_entries: List[Dict[str, Any]] = []
        day_total = 0
        for bucket_name in ('activities', 'meals'):
            bucket = day.get(bucket_name) or []
            if not isinstance(bucket, list):
                continue
            for entry in bucket:
                if not isinstance(entry, dict):
                    continue
                cost = _coerce_cost(entry.get('cost'))
                if cost > per_entry_cap:
                    cost = int(per_entry_cap)
                entry['cost'] = cost
                bucket_entries.append(entry)
                day_total += cost

        if day_total > per_day_cap and day_total > 0:
            ratio = per_day_cap / day_total
            adjusted_total = 0
            for entry in bucket_entries:
                new_cost = int(max(0, round(entry.get('cost', 0) * ratio)))
                entry['cost'] = new_cost
                adjusted_total += new_cost
            day_total = adjusted_total

        day['total_cost'] = int(day_total)

    return itinerary


def normalize_budget_estimate(budget_data: Dict[str, Any], total_budget: float, days: int) -> Dict[str, Any]:
    """Ensure budget breakdown stays within the user-specified limits."""
    if not budget_data or not isinstance(budget_data, dict):
        return budget_data

    safe_total = int(max(100, round(total_budget or 0)))
    days = max(1, int(days or 1))
    safe_daily = int(max(40, round(safe_total / days)))

    budget_data['total_budget'] = min(safe_total, _coerce_cost(budget_data.get('total_budget')) or safe_total)
    budget_data['daily_budget'] = min(safe_daily, _coerce_cost(budget_data.get('daily_budget')) or safe_daily)

    breakdown = budget_data.get('breakdown')
    if not isinstance(breakdown, dict):
        return budget_data

    per_day_base = safe_total / days
    category_caps = {
        'accommodation': per_day_base * 0.55,
        'food': per_day_base * 0.25,
        'activities': per_day_base * 0.3,
        'transport': per_day_base * 0.35,
        'contingency': per_day_base * 0.15,
    }

    tracked_fields = []
    for key, cap in category_caps.items():
        section = breakdown.get(key)
        if not isinstance(section, dict):
            continue
        field = 'subtotal'
        if key in ('activities', 'transport'):
            field = 'estimated'
        if key == 'contingency':
            field = 'amount'

        raw_value = _coerce_cost(section.get(field))
        section[field] = int(min(raw_value, cap)) if cap else raw_value
        tracked_fields.append((section, field, section[field]))

        if 'per_night' in section:
            section['per_night'] = int(min(_coerce_cost(section['per_night']), per_day_base * 0.55))
        if 'per_day' in section:
            section['per_day'] = int(min(_coerce_cost(section['per_day']), per_day_base * 0.25))

    total_categories = sum(value for _, _, value in tracked_fields)
    if total_categories > safe_total and total_categories > 0:
        ratio = safe_total / total_categories
        for section, field, value in tracked_fields:
            section[field] = int(max(0, round(value * ratio)))

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
    if not ordered_pois:
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
