import google.generativeai as genai
import json
import os
import time
import re

genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# Keep the requested model; do not force JSON mode (unsupported on this model)
MODEL = genai.GenerativeModel("gemma-3-4b-it")


ITINERARY_PROMPT = """
You are an expert travel planner creating a comprehensive day-by-day itinerary.

INPUT:
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

Output ONLY valid JSON with:
- Daily budget limits
- Cost per category (accommodation, food, activities, transport)
- Money saving tips specific to this destination
- Estimated total with breakdown

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
                  interests: list, group: str, special_needs: str):
    """Generate comprehensive travel itinerary"""
    
    prompt = ITINERARY_PROMPT.format(
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

        # quick cleanup for occasional code fences
        if text.startswith("```"):
          text = text.replace("```json", "").replace("```", "").strip()

        # Try direct JSON parse first
        try:
          return json.loads(text)
        except json.JSONDecodeError:
          # Fallback: slice first to last brace
          start = text.find("{")
          end = text.rfind("}") + 1
          if start != -1 and end > start:
            cleaned = text[start:end]
            return json.loads(cleaned)
          raise
      except Exception as e:
        if "429" in str(e) and attempt < max_retries - 1:
          wait_time = 15 * (attempt + 1)
          print(f"Rate limit hit. Waiting {wait_time} seconds...")
          time.sleep(wait_time)
        else:
          raise


def budget_agent(destination: str, days: int, budget: float, style: str):
    """Generate detailed budget breakdown"""
    
    prompt = BUDGET_PROMPT.format(
        destination=destination,
        days=days,
        budget=budget,
        style=style
    )

    max_retries = 3
    for attempt in range(max_retries):
      try:
        response = MODEL.generate_content(prompt)
        text = (response.text or "").strip()

        if text.startswith("```"):
          text = text.replace("```json", "").replace("```", "").strip()

        try:
          return json.loads(text)
        except json.JSONDecodeError:
          start = text.find("{")
          end = text.rfind("}") + 1
          if start != -1 and end > start:
            cleaned = text[start:end]
            return json.loads(cleaned)
          raise
      except Exception as e:
        if "429" in str(e) and attempt < max_retries - 1:
          wait_time = 15 * (attempt + 1)
          print(f"Rate limit hit. Waiting {wait_time} seconds...")
          time.sleep(wait_time)
        else:
          raise
