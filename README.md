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
- Distance-aware train fare estimates for India-specific trips
- Live international flight quotes via Kiwi Tequila API (with graceful fallbacks)
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
$env:TEQUILA_API_KEY="your_kiwi_tequila_key_here"      # for live flight quotes (optional)
```

Or use `setx` for persistent variables:
```powershell
setx GOOGLE_API_KEY "your_google_api_key_here"
setx TAVILY_API_KEY "your_tavily_api_key_here"
setx GEOAPIFY_API_KEY "your_geoapify_key_here"
setx TEQUILA_API_KEY "your_kiwi_tequila_key_here"
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

- Missing keys: Ensure `api-keys` exists with two lines and run `./load-api-keys.ps1` in the same terminal before `python api.py`.
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
