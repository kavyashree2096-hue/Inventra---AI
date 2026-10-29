import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'inventra-ai-super-secret-key-2026')
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'inventra-ai-jwt-secret-key-2026')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(days=7)

    # Database configuration
    # Default to PostgreSQL URL as specified, with SQLite fallback if PostgreSQL is unavailable
    RAW_DB_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/inventra_ai')
    
    # We will test connection or fallback in app initialization
    SQLALCHEMY_DATABASE_URI = RAW_DB_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Ollama configuration
    OLLAMA_BASE_URL = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
    OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'llama3.2')
    
    # Uploads
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max
