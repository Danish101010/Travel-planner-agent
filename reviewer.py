from state import TravelState


def reviewer_agent(state: TravelState):
    issues = []

    if state.total_cost > state.budget_limit:
        issues.append("Budget exceeded")

    if state.preferences.get("early_flights") == "no":
        if state.arrival_time:
            hour = int(state.arrival_time.split(":")[0])
            if hour < 10:
                issues.append("Early flight violates preference")

    return {
        "status": "approved" if not issues else "rejected",
        "issues": issues
    }
