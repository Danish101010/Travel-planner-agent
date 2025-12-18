import google.generativeai as genai
import json
import os
import time
import re

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

Output ONLY valid JSON with:
- Daily budget limits
- Cost per category (accommodation, food, activities, transport)
- Money saving tips specific to this destination
- Estimated total with breakdown
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
                  interests: list, group: str, special_needs: str, source: str):
    """Generate comprehensive travel itinerary"""
    
    prompt = ITINERARY_PROMPT.format(
        source=source,
        destination=destination,
        days=days,
        budget=budget,
        style=style,
        interests=", ".join(interests),
        group=group,
        special_needs=special_needs or "None"
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


def budget_agent(destination: str, days: int, budget: float, style: str, source: str):
    """Generate detailed budget breakdown"""
    
    prompt = BUDGET_PROMPT.format(
        destination=destination,
        days=days,
        budget=budget,
        style=style,
        source=source
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
