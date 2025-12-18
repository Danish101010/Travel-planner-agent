# ✈️ Smart Travel Planner

A comprehensive AI-powered travel planning application with a modern web interface. Create personalized day-by-day itineraries tailored to your travel style, budget, and interests.

## Features

✅ **Detailed Day-by-Day Itineraries**
- Morning, afternoon, and evening activities
- Specific times for each activity
- Cost breakdown per activity
- Restaurant recommendations

✅ **Budget Management**
- Detailed budget breakdown by category
- Money-saving tips
- Accommodation, food, activities, and transport costs
- Contingency planning

✅ **Personalized Planning**
- Travel style preferences (Budget, Luxury, Adventure, etc.)
- Interest-based recommendations
- Group type considerations (Solo, Couple, Family, etc.)
- Special needs accommodation

✅ **Smart Recommendations**
- Best time to visit
- Local warnings and tips
- Hidden gems
- Cultural insights

✅ **Interactive Maps & Routing**
- Leaflet + OpenStreetMap tiles for real-time visualization
- Nearby attractions powered by OpenTripMap
- Door-to-door route preview via OpenRouteService
- Clickable POI list that pans/zooms the live map

## Setup Instructions

### 1. Install Dependencies

```powershell
pip install -r requirements.txt
```

### 2. Set Environment Variables

On Windows PowerShell:
```powershell
$env:GOOGLE_API_KEY="your_google_api_key_here"
$env:TAVILY_API_KEY="your_tavily_api_key_here"
$env:OPENTRIPMAP_API_KEY="your_opentripmap_key_here"   # for POIs
$env:ORS_API_KEY="your_openrouteservice_key_here"      # for routing
$env:GEOAPIFY_API_KEY="your_geoapify_key_here"         # for live autocomplete
```

Or use `setx` for persistent variables:
```powershell
setx GOOGLE_API_KEY "your_google_api_key_here"
setx TAVILY_API_KEY "your_tavily_api_key_here"
setx OPENTRIPMAP_API_KEY "your_opentripmap_key_here"
setx ORS_API_KEY "your_openrouteservice_key_here"
setx GEOAPIFY_API_KEY "your_geoapify_key_here"
# Smart Travel Planner — Local Development Guide

A simple guide to run the app locally on Windows (PowerShell). This app serves a modern web UI backed by a Flask API and uses Google Generative AI plus Tavily for research.

## Quick Start

1) Create and activate a virtual environment
```powershell
python -m venv .venv
./.venv/Scripts/Activate.ps1
pip install -r requirements.txt
```

2) Add your API keys in `api-keys`
```text
Line 1: <TAVILY_API_KEY>
Line 2: <GOOGLE_API_KEY>
Line 3 (optional but recommended): <OPENTRIPMAP_API_KEY>
Line 4 (optional but recommended): <ORS_API_KEY>
Line 5 (optional but recommended): <GEOAPIFY_API_KEY>
```

3) Load keys into the current shell and run
```powershell
./load-api-keys.ps1
python api.py
```

Open http://127.0.0.1:5000 in your browser.

4) Provide both Source (departure city) and Destination in the form; the planner will factor the source into itinerary context and budget/transport notes.

## What’s Included

- `api.py`: Flask server and endpoints
- `planner.py`: Itinerary and budget generation using `gemma-3-4b-it`
- `templates/index.html`: UI
- `static/css/style.css`, `static/js/app.js`: Frontend assets (including Leaflet map + POIs)
- `load-api-keys.ps1`: One-liner script to set env vars from `api-keys`

## Health Check and Basics

- Health: `GET http://127.0.0.1:5000/api/health`
- Generate: `POST http://127.0.0.1:5000/api/generate-itinerary`
- Styles: `GET http://127.0.0.1:5000/api/styles`
- Interests: `GET http://127.0.0.1:5000/api/interests`
- Groups: `GET http://127.0.0.1:5000/api/groups`

## Common Issues

- Missing keys: Ensure `api-keys` exists with two lines and run `./load-api-keys.ps1` in the same terminal before `python api.py`.
- 401/403: Recheck keys and that your Google/Tavily accounts are active.
- 429 (rate limit): Wait and retry; avoid rapid repeated requests.
- Port in use: Stop other apps on port 5000 or run `set PORT=5001; python api.py` then open http://127.0.0.1:5001.

## Map, POI & Routing Integrations

- **OpenTripMap**: requires `OPENTRIPMAP_API_KEY`, used for nearby attractions (radius ~5km) and additional metadata such as descriptions, images, and categories.
- **OpenRouteService**: requires `ORS_API_KEY`, used for basic routing between the selected source and destination (driving profile by default).
- **Geoapify Autocomplete**: requires `GEOAPIFY_API_KEY`, used for global place suggestions (falls back to a small offline list if absent).
- **Leaflet / OpenStreetMap**: no key needed; renders the live map, POI markers, and the ORS polyline.

If the optional keys are not provided the rest of the planner continues to work, but the Map & Attractions tab will fall back to an empty state.

# Smart Travel Planner — Local Development Guide

A simple guide to run the app locally on Windows (PowerShell). This app serves a modern web UI backed by a Flask API and uses Google Generative AI plus Tavily for research.

## Quick Start

1) Create and activate a virtual environment
```powershell
python -m venv .venv
./.venv/Scripts/Activate.ps1
pip install -r requirements.txt
```

2) Add your API keys in `api-keys` (two lines)
```text
<TAVILY_API_KEY>
<GOOGLE_API_KEY>
```

3) Load keys into the current shell and run
```powershell
./load-api-keys.ps1
python api.py
```

Open http://127.0.0.1:5000 in your browser.

## What’s Included

- `api.py`: Flask server and endpoints
- `planner.py`: Itinerary and budget generation using `gemma-3-4b-it`
- `templates/index.html`: UI
- `static/css/style.css`, `static/js/app.js`: Frontend assets
- `load-api-keys.ps1`: One-liner script to set env vars from `api-keys`

## Health Check and Basics

- Health: `GET http://127.0.0.1:5000/api/health`
- Generate: `POST http://127.0.0.1:5000/api/generate-itinerary`
- Styles: `GET http://127.0.0.1:5000/api/styles`
- Interests: `GET http://127.0.0.1:5000/api/interests`
- Groups: `GET http://127.0.0.1:5000/api/groups`

## Common Issues

- Missing keys: Ensure `api-keys` exists with two lines and run `./load-api-keys.ps1` in the same terminal before `python api.py`.
- 401/403: Recheck keys and that your Google/Tavily accounts are active.
- 429 (rate limit): Wait and retry; avoid rapid repeated requests.
- Port in use: Stop other apps on port 5000 or run `set PORT=5001; python api.py` then open http://127.0.0.1:5001.

## Notes

- The model is fixed to `gemma-3-4b-it` per app design.
- Keys are loaded into the current PowerShell session only (not persistent).
- For a fresh session, rerun `./load-api-keys.ps1` before starting the server.

Happy hacking! ✈️
