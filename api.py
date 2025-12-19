"""
Travel Planner - Flask Backend API
Production-ready deployment configuration
"""

from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from planner import (
    planner_agent,
    budget_agent,
    normalize_itinerary_costs,
    normalize_budget_estimate,
    apply_meal_pois,
)
from travel_data import (
    autocomplete_destination, 
    get_weather, 
    get_timezone, 
    get_country_info,
    get_travel_advisory,
    get_exchange_rate,
    get_pois,
    get_hotels,
)
from transport_pricing import build_transport_pricing
import os
import traceback
import logging
from datetime import datetime
import time
import copy
from collections import defaultdict, deque

# Configuration
class Config:
    """Application configuration"""
    DEBUG = os.getenv('FLASK_ENV') == 'development'
    TESTING = os.getenv('FLASK_ENV') == 'testing'
    ENV = os.getenv('FLASK_ENV', 'production')
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    CORS_ORIGINS = os.getenv('CORS_ORIGINS', 'http://localhost:3000,http://localhost:5000').split(',')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max request size


# Initialize Flask app
app = Flask(__name__, template_folder='templates', static_folder='static')
app.config.from_object(Config)

# CORS configuration
CORS(app, origins=Config.CORS_ORIGINS, allow_headers=['Content-Type'])

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('travel_planner.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

_exchange_rate_cache = {}
_travel_keywords = ('depart', 'departure', 'flight', 'train', 'transfer', 'journey', 'travel', 'transit')
CACHE_TTL_SECONDS = 3600
_poi_cache = {}
_hotel_cache = {}
_cost_history: defaultdict[str, deque] = defaultdict(lambda: deque(maxlen=120))


def _build_cache_key(name: str, date: str, tag: str) -> str:
    normalized_name = (name or 'unknown').strip().lower() or 'unknown'
    normalized_date = date or 'any'
    return f"{normalized_name}|{normalized_date}|{tag}"


def _get_cached_entry(cache: dict, key: str):
    payload = cache.get(key)
    if not payload:
        return None
    if time.time() - payload['ts'] > CACHE_TTL_SECONDS:
        cache.pop(key, None)
        return None
    return copy.deepcopy(payload['data'])


def _set_cache_entry(cache: dict, key: str, data):
    cache[key] = {
        'data': copy.deepcopy(data),
        'ts': time.time()
    }


def _cached_geo_result(cache: dict, key: str, fetcher, fallback=None):
    cached = _get_cached_entry(cache, key)
    if cached is not None:
        return cached
    try:
        data = fetcher() or fallback or []
    except Exception as exc:
        logger.warning('Geo cache fetch failed for %s: %s', key, exc)
        data = fallback or []
    _set_cache_entry(cache, key, data)
    return data


def _history_average(category: str) -> float:
    values = _cost_history.get(category)
    if not values:
        return 0.0
    return sum(values) / len(values)


def _record_history(category: str, value: int) -> None:
    if value <= 0:
        return
    _cost_history[category].append(value)


def _smooth_cost_outliers(itinerary):
    if not isinstance(itinerary, dict):
        return itinerary
    schedule = itinerary.get('itinerary')
    if not isinstance(schedule, list):
        return itinerary

    updated_days = []
    for day in schedule:
        if not isinstance(day, dict):
            updated_days.append(day)
            continue
        day_copy = copy.deepcopy(day)
        for activity in day_copy.get('activities', []):
            if not isinstance(activity, dict):
                continue
            category = (activity.get('category') or 'general').lower()
            cost = _safe_int(activity.get('estimated_cost') or activity.get('cost'))
            avg = _history_average(category)
            if avg and cost:
                lower = avg * 0.4
                upper = avg * 2.2
                if cost < lower:
                    cost = int(lower)
                elif cost > upper:
                    cost = int(upper)
            if cost:
                activity['estimated_cost'] = cost
                activity['cost'] = cost
                _record_history(category, cost)
        updated_days.append(day_copy)

    itinerary['itinerary'] = updated_days
    return itinerary


def _inject_hotel_recommendations(itinerary, hotels, destination_name):
    if not isinstance(itinerary, dict) or not hotels:
        return itinerary

    itinerary.setdefault('meta', {})['hotels'] = hotels[:5]
    schedule = itinerary.get('itinerary')
    if not isinstance(schedule, list) or not schedule:
        return itinerary

    first_day = schedule[0]
    if not isinstance(first_day, dict):
        return itinerary

    meta = first_day.setdefault('meta', {})
    if meta.get('lodging_injected'):
        return itinerary

    meta['lodging_injected'] = True
    first_day['lodging'] = hotels[:3]
    activities = first_day.get('activities')
    if not isinstance(activities, list):
        activities = []
        first_day['activities'] = activities

    primary = hotels[0]
    anchor_time = '09:00'
    if activities and isinstance(activities[0], dict):
        anchor_time = activities[0].get('time') or anchor_time

    check_in_entry = {
        'time': anchor_time,
        'activity': f"Check-in: {primary.get('name', 'Hotel')}",
        'location': primary.get('address') or destination_name or 'City Center',
        'description': primary.get('description') or 'Suggested lodging near key attractions.',
        'category': 'lodging',
        'estimated_cost': 0,
        'tip': 'Geoapify hotel recommendation'
    }
    activities.insert(0, check_in_entry)

    return itinerary


def _safe_int(value):
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return 0


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _convert_to_usd(amount, currency):
    amount = _safe_float(amount)
    if amount <= 0:
        return 0.0
    currency_code = (currency or 'USD').upper()
    if currency_code == 'USD':
        return amount

    rate = _exchange_rate_cache.get(currency_code)
    if rate is None:
        try:
            payload = get_exchange_rate(currency_code, 'USD')
            rate = _safe_float(payload.get('rate')) if payload else 1.0
        except Exception as exc:
            logger.warning('Exchange lookup failed for %s: %s', currency_code, exc)
            rate = 1.0
        _exchange_rate_cache[currency_code] = rate or 1.0
    return amount * (rate or 1.0)


def _quote_total_cost(quote, fallback_travelers):
    if not isinstance(quote, dict):
        return float('inf')
    if quote.get('group_price') is not None:
        return _safe_float(quote.get('group_price'))
    per_person = _safe_float(quote.get('price_per_person'))
    travelers = quote.get('travelers') or fallback_travelers or 1
    return per_person * max(1, travelers)


def _find_travel_day(schedule):
    for day in schedule:
        if not isinstance(day, dict):
            continue
        text_bits = [day.get('theme', ''), day.get('summary', '')]
        for bucket in ('activities', 'meals'):
            for entry in day.get(bucket, []) or []:
                if isinstance(entry, dict):
                    text_bits.append(entry.get('activity') or entry.get('restaurant') or '')
                    text_bits.append(entry.get('description') or '')
        blob = ' '.join(text_bits).lower()
        if any(keyword in blob for keyword in _travel_keywords):
            return day
    return schedule[0] if schedule else None


def _inject_transport_costs(itinerary, budget, transport_options):
    quotes = (transport_options or {}).get('quotes') or []
    if not itinerary or not isinstance(itinerary, dict) or not quotes:
        return itinerary, budget, None

    if not isinstance(budget, dict):
        budget = {}

    schedule = itinerary.get('itinerary') or []
    if not isinstance(schedule, list) or not schedule:
        return itinerary, budget, None

    travelers = transport_options.get('travelers') or 1
    best_quote = min(quotes, key=lambda q: _quote_total_cost(q, travelers), default=None)
    if not best_quote:
        return itinerary, budget, None

    native_total = _quote_total_cost(best_quote, travelers)
    usd_total = _convert_to_usd(native_total, best_quote.get('currency'))
    if usd_total <= 0:
        return itinerary, budget, None

    target_day = _find_travel_day(schedule)
    if not isinstance(target_day, dict):
        target_day = schedule[0]
    if not isinstance(target_day, dict):
        return itinerary, budget, None

    activities = target_day.get('activities')
    if not isinstance(activities, list):
        activities = []
        target_day['activities'] = activities

    route_label = '{src} -> {dest}'.format(
        src=(transport_options.get('source') or {}).get('label') or 'Departure',
        dest=(transport_options.get('destination') or {}).get('label') or 'Arrival'
    )

    mode_label = (best_quote.get('mode') or 'transport').replace('_', ' ').title()
    provider_label = best_quote.get('provider') or best_quote.get('class_label') or 'Preferred Carrier'
    confidence = (best_quote.get('confidence') or 'estimated').title()
    local_currency = (best_quote.get('currency') or 'USD').upper()
    entry_cost = _safe_int(round(usd_total))

    transport_entry = {
        'time': best_quote.get('departure') or '08:00',
        'activity': f"{mode_label} via {provider_label}",
        'location': route_label,
        'cost': entry_cost,
        'description': f"{mode_label} cost for {travelers} travelers ({local_currency} {int(round(native_total))}).",
        'tip': best_quote.get('notes') or f"{confidence} fare injected automatically."
    }

    activities.insert(0, transport_entry)
    target_day['total_cost'] = _safe_int(target_day.get('total_cost')) + entry_cost

    breakdown = budget.setdefault('breakdown', {}) if isinstance(budget, dict) else {}
    transport_bucket = breakdown.get('transport') if isinstance(breakdown, dict) else None
    if not isinstance(transport_bucket, dict):
        if isinstance(breakdown, dict):
            transport_bucket = {}
            breakdown['transport'] = transport_bucket
        else:
            breakdown = {'transport': {}}
            budget['breakdown'] = breakdown
            transport_bucket = breakdown['transport']
    transport_bucket['estimated'] = _safe_int(transport_bucket.get('estimated')) + entry_cost

    transport_summary = {
        'quote_id': best_quote.get('id'),
        'mode': best_quote.get('mode'),
        'provider': provider_label,
        'currency': local_currency,
        'native_amount': round(native_total, 2),
        'usd_amount': entry_cost,
        'travel_day': target_day.get('day'),
        'notes': best_quote.get('notes'),
    }

    itinerary.setdefault('meta', {})['transport_quote'] = transport_summary
    budget.setdefault('meta', {})['transport_quote'] = transport_summary

    return itinerary, budget, transport_summary


# Error Handlers
@app.errorhandler(400)
def bad_request(error):
    """Handle bad requests"""
    return jsonify({
        'success': False,
        'error': 'Bad request',
        'message': str(error)
    }), 400


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({
        'success': False,
        'error': 'Not found',
        'message': 'The requested resource was not found'
    }), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle internal server errors"""
    logger.error(f'Internal server error: {str(error)}')
    return jsonify({
        'success': False,
        'error': 'Internal server error',
        'message': 'An error occurred processing your request'
    }), 500


# Middleware for request logging
@app.before_request
def log_request():
    """Log incoming requests"""
    logger.info(f'{request.method} {request.path} from {request.remote_addr}')


@app.after_request
def log_response(response):
    """Log outgoing responses"""
    logger.info(f'Response: {response.status_code}')
    return response


@app.route('/')
def index():
    """Serve the main page"""
    try:
        # Cache-buster timestamp to force fresh static asset loads
        return render_template('index.html', cache_buster=int(time.time()))
    except Exception as e:
        logger.error(f'Error serving index: {str(e)}')
        return jsonify({'error': 'Failed to load application'}), 500


@app.route('/static/<path:path>')
def send_static(path):
    """Serve static files"""
    try:
        return send_from_directory('static', path)
    except Exception as e:
        logger.error(f'Error serving static file: {str(e)}')
        return jsonify({'error': 'File not found'}), 404

@app.route('/api/generate-itinerary', methods=['POST'])
def generate_itinerary():
    """Generate a comprehensive travel itinerary"""
    try:
        # Validate request
        if not request.is_json:
            return jsonify({
                'success': False,
                'error': 'Content-Type must be application/json'
            }), 400

        data = request.json
        
        # Validate required fields
        required_fields = ['source', 'destination', 'days', 'budget', 'style', 'interests', 'group']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'Missing required field: {field}'
                }), 400

        # Parse and validate input
        source = str(data.get('source', '')).strip()
        destination = str(data.get('destination', '')).strip()
        days = int(data.get('days', 5))
        budget = float(data.get('budget', 3000))
        style = str(data.get('style', 'Mid-Range')).strip()
        interests = data.get('interests', [])
        group = str(data.get('group', 'Solo')).strip()
        special_needs = str(data.get('special_needs', '')).strip()
        try:
            travelers = int(data.get('travelers') or 1)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'Invalid traveler count'}), 400
        start_date = data.get('start_date')
        source_details = data.get('source_details') or {}
        destination_details = data.get('destination_details') or {}

        source_details.setdefault('name', source)
        destination_details.setdefault('name', destination)

        meal_pois = []
        hotel_recs = []
        try:
            dest_lat = float(destination_details.get('lat'))
            dest_lon = float(destination_details.get('lon'))
        except (TypeError, ValueError):
            dest_lat = dest_lon = None

        if dest_lat is not None and dest_lon is not None:
            cache_tag = _build_cache_key(destination, start_date or '', 'meals')
            meal_pois = _cached_geo_result(
                _poi_cache,
                cache_tag,
                lambda: get_pois(
                    lat=dest_lat,
                    lon=dest_lon,
                    kinds='foods,cafes,restaurants',
                    radius=1500,
                    limit=20,
                ),
                fallback=[]
            )

            hotel_tag = _build_cache_key(destination, start_date or '', 'hotels')
            hotel_recs = _cached_geo_result(
                _hotel_cache,
                hotel_tag,
                lambda: get_hotels(
                    lat=dest_lat,
                    lon=dest_lon,
                    radius=2500,
                    limit=6,
                ),
                fallback=[]
            )

        # Validate input constraints
        if not source:
            return jsonify({'success': False, 'error': 'Source cannot be empty'}), 400
        if not destination:
            return jsonify({'success': False, 'error': 'Destination cannot be empty'}), 400
        if days < 1 or days > 30:
            return jsonify({'success': False, 'error': 'Days must be between 1 and 30'}), 400
        if budget < 500 or budget > 100000:
            return jsonify({'success': False, 'error': 'Budget must be between 500 and 100000'}), 400
        if not isinstance(interests, list) or len(interests) == 0:
            return jsonify({'success': False, 'error': 'At least one interest must be selected'}), 400
        if travelers < 1:
            return jsonify({'success': False, 'error': 'Travelers must be at least 1'}), 400
        if group.lower() != 'solo' and travelers < 2:
            return jsonify({'success': False, 'error': 'Please provide the number of travelers for non-solo trips'}), 400

        logger.info(
            'Generating itinerary: %s -> %s (%s days, $%s, %s travelers)',
            source,
            destination,
            days,
            budget,
            travelers,
        )

        # Generate itinerary
        itinerary_raw = planner_agent(destination, days, budget, style, interests, group, special_needs, source, travelers)
        if not itinerary_raw:
            raise ValueError('Planner failed to return itinerary data')
        itinerary = normalize_itinerary_costs(copy.deepcopy(itinerary_raw), budget, days)
        if meal_pois:
            itinerary = apply_meal_pois(itinerary, meal_pois, itinerary_raw)
            itinerary = normalize_itinerary_costs(itinerary, budget, days)
        if hotel_recs:
            itinerary = _inject_hotel_recommendations(itinerary, hotel_recs, destination)
        
        # Generate budget breakdown
        budget_raw = budget_agent(destination, days, budget, style, source, travelers)
        if not budget_raw:
            raise ValueError('Budget agent failed to return data')
        budget_info = normalize_budget_estimate(copy.deepcopy(budget_raw), budget, days)

        transport_options = build_transport_pricing(
            source_details=source_details,
            destination_details=destination_details,
            departure_date=start_date,
            travelers=travelers,
        )

        itinerary, budget_info, transport_summary = _inject_transport_costs(
            itinerary,
            budget_info,
            transport_options,
        )
        itinerary = _smooth_cost_outliers(itinerary)
        if transport_summary:
            transport_options['applied_quote'] = transport_summary

        logger.info(f'Successfully generated itinerary for {destination}')

        return jsonify({
            'success': True,
            'itinerary': itinerary,
            'itinerary_normalized': itinerary,
            'itinerary_raw': itinerary_raw,
            'budget': budget_info,
            'budget_normalized': budget_info,
            'budget_raw': budget_raw,
            'transport': transport_options,
            'hotels': hotel_recs,
            'group': {
                'type': group,
                'travelers': travelers,
                'start_date': start_date
            },
            'timestamp': datetime.utcnow().isoformat()
        }), 200

    except ValueError as e:
        logger.error(f'Value error in generate_itinerary: {str(e)}')
        return jsonify({
            'success': False,
            'error': 'Invalid input values',
            'message': str(e)
        }), 400
    except Exception as e:
        logger.error(f'Error generating itinerary: {str(e)}', exc_info=True)
        return jsonify({
            'success': False,
            'error': 'Failed to generate itinerary',
            'message': 'Please try again later'
        }), 500


@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint for deployment monitoring"""
    try:
        env_vars = {
            'GOOGLE_API_KEY': bool(os.getenv('GOOGLE_API_KEY')),
            'TAVILY_API_KEY': bool(os.getenv('TAVILY_API_KEY')),
            'GEOAPIFY_API_KEY': bool(os.getenv('GEOAPIFY_API_KEY'))
        }
        
        return jsonify({
            'status': 'healthy',
            'environment': Config.ENV,
            'timestamp': datetime.utcnow().isoformat(),
            'env_vars_set': env_vars
        }), 200
    except Exception as e:
        logger.error(f'Health check failed: {str(e)}')
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500


@app.route('/api/status', methods=['GET'])
def status():
    """Get application status and configuration"""
    return jsonify({
        'app': 'Travel Planner API',
        'version': '1.0.0',
        'environment': Config.ENV,
        'debug': Config.DEBUG,
        'timestamp': datetime.utcnow().isoformat()
    }), 200


@app.route('/api/styles', methods=['GET'])
def get_styles():
    """Get available travel styles"""
    styles = ["Budget", "Mid-Range", "Luxury", "Adventure", "Cultural", "Relaxation"]
    return jsonify(styles)


@app.route('/api/interests', methods=['GET'])
def get_interests():
    """Get available interests"""
    interests = [
        "History & Culture", "Food & Dining", "Adventure Sports", "Nature",
        "Nightlife", "Shopping", "Beach", "Mountains", "Art & Museums", "Photography"
    ]
    return jsonify(interests)


@app.route('/api/groups', methods=['GET'])
def get_groups():
    """Get available group types"""
    groups = ["Solo", "Couple", "Family", "Friends Group", "Corporate"]
    return jsonify(groups)


@app.route('/api/autocomplete', methods=['GET'])
def api_autocomplete():
    """Autocomplete destination using free Nominatim API"""
    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return jsonify([]), 200
    
    try:
        results = autocomplete_destination(query)
        logger.info(f"Autocomplete: {query} -> {len(results)} results")
        return jsonify(results), 200
    except Exception as e:
        logger.error(f"Autocomplete error: {str(e)}")
        return jsonify({'error': 'Autocomplete service unavailable'}), 500


@app.route('/api/weather', methods=['POST'])
def api_weather():
    """Get weather forecast for destination"""
    try:
        data = request.get_json(force=True)
        destination = str(data.get('destination', '')).strip()
        lat = float(data.get('lat', 0))
        lon = float(data.get('lon', 0))
        days = int(data.get('days', 7))

        if not destination or lat == 0 or lon == 0:
            return jsonify({'error': 'Missing destination or coordinates'}), 400

        weather = get_weather(lat, lon, days)
        if not weather:
            return jsonify({'error': 'Weather service unavailable'}), 500

        logger.info(f"Weather fetched for {destination}")
        return jsonify(weather), 200
    except Exception as e:
        logger.error(f"Weather API error: {str(e)}")
        return jsonify({'error': 'Failed to fetch weather'}), 500


@app.route('/api/timezone', methods=['POST'])
def api_timezone():
    """Get timezone for coordinates"""
    try:
        data = request.json
        lat = float(data.get('lat', 0))
        lon = float(data.get('lon', 0))

        if lat == 0 or lon == 0:
            return jsonify({'error': 'Missing coordinates'}), 400

        tz = get_timezone(lat, lon)
        if not tz:
            return jsonify({'error': 'Timezone service unavailable'}), 500

        logger.info(f"Timezone fetched for {lat},{lon}: {tz['timezone']}")
        return jsonify(tz), 200
    except Exception as e:
        logger.error(f"Timezone API error: {str(e)}")
        return jsonify({'error': 'Failed to fetch timezone'}), 500


@app.route('/api/travel-advisory', methods=['GET'])
def api_travel_advisory():
    """Get travel advisory for a country"""
    try:
        country_code = request.args.get('country', '').strip().upper()
        if not country_code or len(country_code) != 2:
            return jsonify({'error': 'Invalid country code (must be 2-letter ISO code)'}), 400

        advisory = get_travel_advisory(country_code)
        if not advisory:
            return jsonify({'error': 'Advisory not available for this country'}), 404

        logger.info(f"Travel advisory fetched for {country_code}: {advisory.get('level')}")
        return jsonify(advisory), 200
    except Exception as e:
        logger.error(f"Travel advisory error: {str(e)}")
        return jsonify({'error': 'Failed to fetch advisory'}), 500


@app.route('/api/country-info', methods=['GET'])
def api_country_info():
    """Get country information including currency"""
    try:
        country_name = request.args.get('country', '').strip()
        if not country_name:
            return jsonify({'error': 'Missing country name'}), 400

        country_info = get_country_info(country_name)
        if not country_info:
            return jsonify({'error': 'Country not found'}), 404

        logger.info(f"Country info fetched for {country_name}: {country_info.get('currency_code')}")
        return jsonify(country_info), 200
    except Exception as e:
        logger.error(f"Country info error: {str(e)}")
        return jsonify({'error': 'Failed to fetch country info'}), 500


@app.route('/api/exchange-rate', methods=['GET'])
def api_exchange_rate():
    """Get currency exchange rate"""
    try:
        from_currency = request.args.get('from', 'USD').strip().upper()
        to_currency = request.args.get('to', 'EUR').strip().upper()

        if len(from_currency) != 3 or len(to_currency) != 3:
            return jsonify({'error': 'Invalid currency code (must be 3-letter ISO code)'}), 400

        rate = get_exchange_rate(from_currency, to_currency)
        if not rate:
            return jsonify({'error': 'Exchange rate not available'}), 404

        logger.info(f"Exchange rate fetched: {from_currency} -> {to_currency} = {rate.get('rate')}")
        return jsonify(rate), 200
    except Exception as e:
        logger.error(f"Exchange rate error: {str(e)}")
        return jsonify({'error': 'Failed to fetch exchange rate'}), 500


if __name__ == '__main__':
    # Development server only - use Gunicorn in production
    if Config.ENV == 'development':
        app.run(
            host='0.0.0.0',
            port=int(os.getenv('PORT', 5000)),
            debug=True,
            threaded=True
        )
    else:
        # Production: use Gunicorn instead
        logger.warning('Running in production mode. Use Gunicorn for production deployments.')
        app.run(
            host='0.0.0.0',
            port=int(os.getenv('PORT', 5000)),
            debug=False,
            threaded=True
        )
