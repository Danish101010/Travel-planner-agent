import google.generativeai as genai
import json
import os
import time
import re
from typing import Any, Dict, List

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
