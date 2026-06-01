# Smart Travel Planner: Comprehensive Architecture Review

This document serves as the complete technical manifesto and architecture review of the **Smart Travel Planner**. It details every component, logic flow, API integration, and architectural pattern used to build this multi-agent, context-aware travel application.

---

## 1. Application Overview

The Smart Travel Planner is an advanced, AI-powered travel orchestrator. Unlike simple chatbots, it features a highly dynamic, **Dual-Currency Sequential Pipeline** that bridges real-world constraints (like live flight costs and local exchange rates) with the creative generation of Google's Gemini models. It plans day-by-day itineraries, exact transit routes, and granular budget breakdowns, all wrapped in a premium **Glassmorphism** user interface.

---

## 2. Core Architecture & Multi-Agent Pipeline

The system is split into an elegant Flask backend (for orchestration and data aggregation) and a highly responsive JavaScript frontend.

### A. The Agentic Core (`planner.py`)
This is the "brain" of the application, utilizing the `google.genai` SDK to instantiate specialized agents:
*   **The Routing Agent**: Analyzes geography. If the user is traveling from a small town (e.g., Buxar) to a major hub (e.g., Tokyo), it generates a generalized, multi-modal routing strategy (e.g., "Take a train to Varanasi, then fly to Tokyo").
*   **The Budget Agent**: Operates to generate a categorical cost breakdown (accommodation, food, activities) based on the exact user parameters and the destination's local currency.
*   **The Planner Agent**: Instructed via a rigid `ITINERARY_PROMPT` to output structured JSON. It receives the *exact categorical financial breakdown* from the Budget Agent as a strict constraint, allowing it to mathematically build a natively accurate day-by-day schedule.

#### The Planner Prompt Engine (`ITINERARY_PROMPT`)
The core reasoning of the application is governed by strict prompting rules designed to curb LLM hallucinations. The prompt explicitly forces the Planner Agent to:
*   **Adhere to Strict Constraints**: Obey the injected budget breakdown category by category (e.g., spending limits on food vs. activities).
*   **Enforce Native Currency**: Calculate costs natively in the Destination Currency. It is strictly banned from using USD default estimations unless specifically requested.
*   **Generate Micro-Logistics**: Populate a mandatory `transit_to_next` field for every single activity, generating exact inter-city transit instructions (e.g., '15m subway via Marunouchi Line') instead of just listing static locations.
*   **Standardize Math**: Output only single integer values for costs (preventing ambiguous ranges like "10-20").

### B. The Sequential Stateful Chain (`api.py`)
The application executes the AI agents in a strict **Sequential Stateful Chain** to ensure financial accuracy and context sharing:
1.  **Transport & On-Ground Math**: The backend queries live transport costs (e.g., flights) in the user's **Source Currency**. It deducts this from the total budget, converts the remainder to the **Destination Currency**, and sets the `on_ground_dest` budget.
2.  **Budget Generation**: The `budget_agent` runs first. It takes the `on_ground_dest` budget and splits it into categories (e.g., 20% food, 30% activities).
3.  **Planner Generation**: The `planner_agent` runs next. The categorical breakdown from the Budget Agent is explicitly injected into the Planner's prompt. This provides the Planner with strict financial guardrails *before* it generates activities, resulting in highly accurate native planning.

### C. True Native Pricing & Normalization
*   **No Artificial Clamping**: The system does **not** mathematically rewrite or scale down the AI's generated costs. If the AI (or Geoapify) generates a cost that goes over budget, it is passed through exactly as generated. This guarantees authentic, true-to-world pricing instead of artificially suppressed values.
*   **Type Coercion**: The normalizers (`normalize_itinerary_costs` and `normalize_budget_estimate`) simply ensure that the output values are valid integers and properly compute the daily totals.

### D. Data Integration & Enrichment (`travel_data.py` & `transport_pricing.py`)
*   **`transport_pricing.py`**: Integrates TravelPayouts (flights) and IRCTC (Indian rail). If APIs fail, it relies on a robust Haversine distance-based math heuristic. The inbound flight/train is strictly injected onto **Day 1** of the itinerary.
*   **`travel_data.py`**: Uses Geoapify to autocomplete locations and extract highly specific coordinates. 
*   **POI Injection Logic**: It fetches real-world restaurants (5km radius) to overwrite the LLM's generic placeholders. It implements a safety check: if Geoapify finds fewer than 6 distinct restaurants, the backend aborts the injection and falls back to the AI's native restaurants to prevent heavy repetition across a multi-day trip.

---

## 3. Frontend Architecture (`app.js` & `style.css`)

The presentation layer is built on Vanilla HTML/JS/CSS, prioritizing performance and aesthetics.

*   **Premium Glassmorphism**: The UI features smooth backdrop filters, gradient borders, and micro-animations to create a premium feel.
*   **Real-Time Currency Detection**: The instant a user selects a departure city, the UI resolves the local currency and updates the budget input label (e.g., "Total Budget (INR)").
*   **Intra-Day Transit (`transit_to_next`)**: The UI explicitly maps and renders exact transit instructions (e.g., "🚇 15m subway via Marunouchi Line") between individual activities within a day.
*   **Dual-Currency Rendering**: The frontend splits the display. The Transport snapshot card is rendered in the Source Currency, while the entire day-by-day itinerary and meal tracks are rendered strictly in the Destination Currency without any secondary exchange-rate conversions.

---

## 4. API Dependencies & Environment

*   **`GOOGLE_API_KEY`**: Absolutely required to power the `google.genai` Client.
*   **`TAVILY_API_KEY`**: Powers the dynamic web-search capabilities of the executor agents.
*   **`GEOAPIFY_API_KEY`**: Crucial for location autocompletion, lat/lon resolution, and fetching real-world POIs.
*   **`TRAVELPAYOUTS_TOKEN`**: Required to fetch live, real-world flight quotes.

---

## 5. Defensive Design & Error Handling

*   **JSON Healing**: The application utilizes an aggressive `_parse_json_safe()` function to sanitize LLM output, stripping out markdown formatting, repairing trailing commas, and fixing invalid string literals before parsing.
*   **Model Fallbacks**: The system actively handles `429 Too Many Requests` and `503 Service Unavailable` errors from Gemini by implementing automated exponential backoff retries across all three agents, guaranteeing resilience during Google API demand spikes.
