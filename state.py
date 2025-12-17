from pydantic import BaseModel
from typing import Dict, List, Optional


class TravelState(BaseModel):
    destination: str
    days: int
    budget_limit: float

    total_cost: float = 0.0

    preferences: Dict[str, str] = {
        "early_flights": "no"
    }

    flight: Optional[Dict] = None
    hotel: Optional[Dict] = None
    food: List[Dict] = []

    arrival_time: Optional[str] = None
