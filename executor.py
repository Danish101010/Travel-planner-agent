from tavily import TavilyClient
from state import TravelState
import re
import os

tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))


def extract_price(text):
    match = re.search(r"\$([0-9]+)", text)
    return int(match.group(1)) if match else None


def execute_task(task, state: TravelState):
    task_text = task["task"].lower()

    if "flight" in task_text:
        result = tavily.search(
            query=f"cheap round trip flight to {state.destination}",
            max_results=3
        )
        price = extract_price(result["results"][0]["content"]) or 800
        state.flight = {
            "price": price,
            "arrival_time": "19:30"
        }
        state.total_cost += price

    elif "hotel" in task_text:
        result = tavily.search(
            query=f"budget hotel in {state.destination}",
            max_results=3
        )

        hotels = []
        for r in result["results"]:
            hotels.append({
                "name": r["title"],
                "price_per_night": extract_price(r["content"]) or 70
            })

        return hotels  # human-in-loop

    elif "food" in task_text:
        daily = 25
        total = daily * state.days
        state.food = [{
            "daily_cost": daily,
            "total_cost": total
        }]
        state.total_cost += total
