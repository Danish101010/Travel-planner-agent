"""
Travel Planner - Flask Backend API
Production-ready deployment configuration
"""

from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from planner import planner_agent, budget_agent
from travel_data import (
    autocomplete_destination, 
    get_weather, 
    get_timezone, 
    get_country_info,
    get_travel_advisory,
    get_exchange_rate,
    get_pois,
    get_route_directions
)
import os
import traceback
import logging
from datetime import datetime
import time

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

        logger.info(f'Generating itinerary: {source} -> {destination} ({days} days, ${budget})')

        # Generate itinerary
        itinerary = planner_agent(destination, days, budget, style, interests, group, special_needs, source)
        
        # Generate budget breakdown
        budget_info = budget_agent(destination, days, budget, style, source)

        logger.info(f'Successfully generated itinerary for {destination}')

        return jsonify({
            'success': True,
            'itinerary': itinerary,
            'budget': budget_info,
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
            'OPENTRIPMAP_API_KEY': bool(os.getenv('OPENTRIPMAP_API_KEY')),
            'ORS_API_KEY': bool(os.getenv('ORS_API_KEY')),
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


@app.route('/api/pois', methods=['POST'])
def api_pois():
    """Get POIs near coordinates via OpenTripMap"""
    try:
        if not request.is_json:
            return jsonify({'error': 'Content-Type must be application/json'}), 400

        data = request.json or {}
        lat = float(data.get('lat', 0))
        lon = float(data.get('lon', 0))
        radius = int(data.get('radius', 4000))
        limit = int(data.get('limit', 15))
        kinds = data.get('kinds')

        if not lat or not lon:
            return jsonify({'error': 'Latitude and longitude are required'}), 400

        pois = get_pois(lat, lon, kinds=kinds, radius=radius, limit=limit)
        return jsonify({'pois': pois}), 200
    except ValueError as e:
        logger.warning(f"POI input error: {str(e)}")
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"POI service error: {str(e)}")
        return jsonify({'error': 'Failed to fetch POIs'}), 500


@app.route('/api/route', methods=['POST'])
def api_route():
    """Get basic route between source and destination using OpenRouteService"""
    try:
        if not request.is_json:
            return jsonify({'error': 'Content-Type must be application/json'}), 400

        data = request.json or {}
        source = data.get('source') or {}
        destination = data.get('destination') or {}
        profile = data.get('profile', 'driving-car')

        if not source or not destination:
            return jsonify({'error': 'Source and destination objects are required'}), 400

        route = get_route_directions(source, destination, profile=profile)
        if not route:
            return jsonify({'error': 'Route not available'}), 404

        return jsonify({'route': route}), 200
    except ValueError as e:
        logger.warning(f"Route input error: {str(e)}")
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Route service error: {str(e)}")
        return jsonify({'error': 'Failed to fetch route'}), 500


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
