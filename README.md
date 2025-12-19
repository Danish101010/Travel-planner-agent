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

✅ **Transport Pricing Intelligence**
- Live Indian Railways fares via IRCTC (RapidAPI free tier) with distance-aware heuristics as fallback
- Free TravelPayouts flight fares, with distance heuristics when live data is unavailable
- Automatic scaling for couples, families, or teams so costs stay accurate

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
$env:GEOAPIFY_API_KEY="your_geoapify_key_here"         # for autocomplete + POIs
$env:TRAVELPAYOUTS_TOKEN="your_travelpayouts_token"     # for free flight fares fallback
$env:IRCTC_RAPIDAPI_KEY="your_irctc_rapidapi_key"       # for live Indian Rail fares (optional)
# Optional if RapidAPI host differs from default
# $env:IRCTC_RAPIDAPI_HOST="irctc1.p.rapidapi.com"
```

Or use `setx` for persistent variables:
```powershell
setx GOOGLE_API_KEY "your_google_api_key_here"
setx TAVILY_API_KEY "your_tavily_api_key_here"
setx GEOAPIFY_API_KEY "your_geoapify_key_here"
setx TRAVELPAYOUTS_TOKEN "your_travelpayouts_token"
setx IRCTC_RAPIDAPI_KEY "your_irctc_rapidapi_key"
rem Optional if RapidAPI host differs from default
rem setx IRCTC_RAPIDAPI_HOST "irctc1.p.rapidapi.com"

The TravelPayouts token comes from https://www.travelpayouts.com/ (free tier). Indian Rail fares use
the `irctc1` RapidAPI collection; grab a free RapidAPI key and assign it to `IRCTC_RAPIDAPI_KEY`.
```

Open http://127.0.0.1:5000 in your browser.

4) Provide both Source (departure city) and Destination in the form; the planner will factor the source into itinerary context and budget/transport notes.

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

- Missing keys: Ensure `api-keys` includes at least Tavily + Google entries (ordered lines or `KEY=VALUE`) and run `./load-api-keys.ps1` in the same terminal before `python api.py`.
- 401/403: Recheck keys and that your Google/Tavily accounts are active.
- 429 (rate limit): Wait and retry; avoid rapid repeated requests.
- Port in use: Stop other apps on port 5000 or run `set PORT=5001; python api.py` then open http://127.0.0.1:5001.

# Smart Travel Planner — Local Development Guide

A simple guide to run the app locally on Windows (PowerShell). This app serves a modern web UI backed by a Flask API and uses Google Generative AI plus Tavily for research.

## Quick Start

1) Create and activate a virtual environment
```powershell
python -m venv .venv
./.venv/Scripts/Activate.ps1
pip install -r requirements.txt
```

2) Add your API keys in `api-keys` (ordered lines or `KEY=VALUE`)—minimum first two values
```text
TAVILY_API_KEY=xxxxxxxxxxxxxxxx
GOOGLE_API_KEY=yyyyyyyyyyyyyyyy
GEOAPIFY_API_KEY=optional-but-useful
TRAVELPAYOUTS_TOKEN=optional-free-flight-fares
IRCTC_RAPIDAPI_KEY=optional-indian-rail
# IRCTC_RAPIDAPI_HOST=irctc1.p.rapidapi.com   (only if you need to override)
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

- Missing keys: Ensure `api-keys` includes at least Tavily + Google entries (ordered lines or `KEY=VALUE`) and run `./load-api-keys.ps1` in the same terminal before `python api.py`.
- 401/403: Recheck keys and that your Google/Tavily accounts are active.
- 429 (rate limit): Wait and retry; avoid rapid repeated requests.
- Port in use: Stop other apps on port 5000 or run `set PORT=5001; python api.py` then open http://127.0.0.1:5001.

## Notes

- The model is fixed to `gemma-3-4b-it` per app design.
- Keys are loaded into the current PowerShell session only (not persistent).
- For a fresh session, rerun `./load-api-keys.ps1` before starting the server.

Happy hacking! ✈️
