from state import TravelState
from planner import planner_agent
from executor import execute_task
from reviewer import reviewer_agent
from human import choose_option


def run():
    state = TravelState(
        destination="Tokyo",
        days=3,
        budget_limit=2000,
        preferences={"early_flights": "no"}
    )

    goal = "Plan a 3-day trip to Tokyo under $2000"

    tasks = planner_agent(goal)

    for task in tasks:
        result = execute_task(task, state)

        if isinstance(result, list):  # Human-in-loop
            chosen = choose_option(result)
            state.hotel = chosen
            cost = chosen["price_per_night"] * state.days
            state.total_cost += cost

    review = reviewer_agent(state)

    print("\n📋 ITINERARY CARD\n")
    print(state.model_dump())
    print(f"\n💰 Budget Used: ${state.total_cost}")
    print("Review:", review["status"])


if __name__ == "__main__":
    run()
