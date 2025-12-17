"""
Travel Planner - Flask Backend API
Production-ready deployment configuration
"""

from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from planner import planner_agent, budget_agent
import os
import traceback
import logging
from datetime import datetime

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
        return render_template('index.html')
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
        required_fields = ['destination', 'days', 'budget', 'style', 'interests', 'group']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'Missing required field: {field}'
                }), 400

        # Parse and validate input
        destination = str(data.get('destination', '')).strip()
        days = int(data.get('days', 5))
        budget = float(data.get('budget', 3000))
        style = str(data.get('style', 'Mid-Range')).strip()
        interests = data.get('interests', [])
        group = str(data.get('group', 'Solo')).strip()
        special_needs = str(data.get('special_needs', '')).strip()

        # Validate input constraints
        if not destination:
            return jsonify({'success': False, 'error': 'Destination cannot be empty'}), 400
        if days < 1 or days > 30:
            return jsonify({'success': False, 'error': 'Days must be between 1 and 30'}), 400
        if budget < 500 or budget > 100000:
            return jsonify({'success': False, 'error': 'Budget must be between 500 and 100000'}), 400
        if not isinstance(interests, list) or len(interests) == 0:
            return jsonify({'success': False, 'error': 'At least one interest must be selected'}), 400

        logger.info(f'Generating itinerary: {destination} ({days} days, ${budget})')

        # Generate itinerary
        itinerary = planner_agent(destination, days, budget, style, interests, group, special_needs)
        
        # Generate budget breakdown
        budget_info = budget_agent(destination, days, budget, style)

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
            'TAVILY_API_KEY': bool(os.getenv('TAVILY_API_KEY'))
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
