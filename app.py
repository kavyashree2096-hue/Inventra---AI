import os
from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

from config import Config
from models import db
from routes import register_blueprints
from utils.seed_data import seed_database

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Enable CORS for React frontend
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # JWT Authentication Manager
    jwt = JWTManager(app)

    # Database connection test & graceful fallback
    raw_db_url = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    base_dir = os.path.abspath(os.path.dirname(__file__))
    if raw_db_url.startswith('postgresql'):
        try:
            # Test if PostgreSQL is reachable
            engine = create_engine(raw_db_url, connect_args={'connect_timeout': 2})
            conn = engine.connect()
            conn.close()
            print("Successfully connected to PostgreSQL database!")
        except Exception as e:
            fallback_sqlite = f"sqlite:///{os.path.join(base_dir, 'inventra_ai.db')}"
            print(f"PostgreSQL connection offline or unavailable ({e}). Falling back to local SQLite: {fallback_sqlite}")
            app.config['SQLALCHEMY_DATABASE_URI'] = fallback_sqlite

    # Initialize SQLAlchemy ORM
    db.init_app(app)

    # Register all modular REST API blueprints
    register_blueprints(app)

    # Health check endpoint
    @app.route('/api/health', methods=['GET'])
    def health_check():
        db_type = 'PostgreSQL' if 'postgresql' in app.config['SQLALCHEMY_DATABASE_URI'] else 'SQLite'
        return jsonify({
            'status': 'healthy',
            'application': 'Inventra AI - Retail Demand Prediction & Procurement Intelligence',
            'database': db_type,
            'version': '1.0.0'
        }), 200

    # Generic error handlers
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({'error': 'Resource not found'}), 404

    @app.errorhandler(500)
    def internal_error(e):
        return jsonify({'error': 'Internal server error'}), 500

    # Auto create tables and seed demo data on initial startup
    with app.app_context():
        db.create_all()
        seed_database()

    return app

if __name__ == '__main__':
    app = create_app()
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
