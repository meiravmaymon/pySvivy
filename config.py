"""
Configuration module for Svivy Municipal System.

מודול הגדרות מרכזי עבור מערכת סביבי - ניהול פרוטוקולים עירוניים

Usage:
    from config import config

    # Access configuration
    db_path = config.DATABASE_PATH
    tesseract_path = config.TESSERACT_PATH

Environment variables can be set in a .env file in the project root.
"""
import os
import logging
from pathlib import Path

# Base directory
BASE_DIR = Path(__file__).resolve().parent

# Load .env file if it exists
def load_dotenv():
    """Load environment variables from .env file."""
    env_file = BASE_DIR / '.env'
    if env_file.exists():
        try:
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if not line or line.startswith('#'):
                        continue
                    # Parse KEY=VALUE
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        # Remove quotes if present
                        if value and value[0] in ('"', "'") and value[-1] == value[0]:
                            value = value[1:-1]
                        # Only set if not already set (env vars take precedence)
                        if key not in os.environ:
                            os.environ[key] = value
        except Exception as e:
            print(f"Warning: Could not load .env file: {e}")

# Load .env on module import
load_dotenv()

# Configure logging
def setup_logging(level=logging.INFO, log_file=None):
    """
    Configure logging for the application.

    Args:
        level: Logging level (default: INFO)
        log_file: Optional log file path
    """
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    handlers = [logging.StreamHandler()]

    if log_file:
        log_dir = BASE_DIR / 'logs'
        log_dir.mkdir(exist_ok=True)
        handlers.append(logging.FileHandler(log_dir / log_file, encoding='utf-8'))

    logging.basicConfig(
        level=level,
        format=log_format,
        handlers=handlers
    )

    # Reduce noise from external libraries
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('werkzeug').setLevel(logging.WARNING)


class Config:
    """Base configuration class."""

    # Application
    APP_NAME = 'Svivy Municipal System'
    VERSION = '2.2'
    DEBUG = os.environ.get('SVIVY_DEBUG', 'false').lower() == 'true'

    # Database
    DATABASE_NAME = os.environ.get('SVIVY_DB_NAME', 'svivyNew.db')
    DATABASE_DIR = os.environ.get('SVIVY_DB_DIR', str(BASE_DIR))
    DATABASE_PATH = os.path.join(DATABASE_DIR, DATABASE_NAME)
    DATABASE_URL = f'sqlite:///{DATABASE_PATH}'

    # Web App
    # IMPORTANT: Set SVIVY_SECRET_KEY environment variable in production!
    SECRET_KEY = os.environ.get('SVIVY_SECRET_KEY', 'dev-only-change-in-production-' + str(hash(str(BASE_DIR)))[:16])
    UPLOAD_FOLDER = os.environ.get('SVIVY_UPLOAD_FOLDER', str(BASE_DIR / 'uploads'))
    MAX_CONTENT_LENGTH = int(os.environ.get('SVIVY_MAX_UPLOAD_MB', '50')) * 1024 * 1024

    # OCR / Tesseract
    TESSERACT_PATH = os.environ.get(
        'TESSERACT_PATH',
        r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    )
    TESSDATA_PREFIX = os.environ.get(
        'TESSDATA_PREFIX',
        str(BASE_DIR / 'tessdata')
    )

    # LLM / Ollama
    OLLAMA_HOST = os.environ.get('OLLAMA_HOST', 'http://localhost:11434')
    OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'gemma3:1b')
    OLLAMA_TIMEOUT = int(os.environ.get('OLLAMA_TIMEOUT', '120'))

    # LLM / Google Gemini
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', os.environ.get('GOOGLE_API_KEY', ''))
    GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-2.0-flash-lite')
    GEMINI_REQUESTS_PER_MINUTE = int(os.environ.get('GEMINI_REQUESTS_PER_MINUTE', '15'))
    GEMINI_DAILY_TOKEN_LIMIT = int(os.environ.get('GEMINI_DAILY_TOKEN_LIMIT', '1000000'))

    # Folders
    PROTOCOLS_FOLDER = os.environ.get('SVIVY_PROTOCOLS_FOLDER', str(BASE_DIR / 'protocols_pdf'))
    OCR_RESULTS_FOLDER = os.environ.get('SVIVY_OCR_RESULTS_FOLDER', str(BASE_DIR / 'ocr_results'))
    LOGS_FOLDER = str(BASE_DIR / 'logs')

    # Source folder for PDF protocols - תיקיית מקור לפרוטוקולים
    SOURCE_PDF_FOLDER = os.environ.get(
        'SVIVY_SOURCE_PDF_FOLDER',
        r'C:\SvivyPro\sviviy\protocolPdf\yehud-monoson\cityCuncilProtocol'
    )

    # Processed files destination - תיקיית יעד לקבצים שעובדו
    WORKED_ON_FOLDER = os.environ.get(
        'SVIVY_WORKED_ON_FOLDER',
        r'C:\SvivyPro\sviviy\protocolPdf\yehud-monoson\cityCuncilProtocol\worked_on'
    )

    # Learning data
    LEARNING_DATA_FILE = str(BASE_DIR / 'ocr_learning_data.json')
    CHANGE_LOG_FILE = str(BASE_DIR / 'ocr_changes_log.json')

    @classmethod
    def ensure_folders(cls):
        """Create required folders if they don't exist."""
        folders = [
            cls.UPLOAD_FOLDER,
            cls.PROTOCOLS_FOLDER,
            cls.OCR_RESULTS_FOLDER,
            cls.LOGS_FOLDER,
            os.path.join(cls.PROTOCOLS_FOLDER, 'worked_on'),
        ]
        for folder in folders:
            Path(folder).mkdir(parents=True, exist_ok=True)

    @classmethod
    def validate(cls):
        """Validate configuration and dependencies."""
        issues = []

        # Check Tesseract
        if not os.path.exists(cls.TESSERACT_PATH):
            issues.append(f"Tesseract not found at: {cls.TESSERACT_PATH}")

        # Check tessdata
        if not os.path.exists(cls.TESSDATA_PREFIX):
            issues.append(f"Tessdata folder not found at: {cls.TESSDATA_PREFIX}")

        # Check database folder
        if not os.path.exists(cls.DATABASE_DIR):
            issues.append(f"Database directory not found: {cls.DATABASE_DIR}")

        return issues

    @classmethod
    def print_config(cls):
        """Print current configuration (for debugging)."""
        print("=" * 50)
        print(f"  {cls.APP_NAME} v{cls.VERSION}")
        print("=" * 50)
        print(f"  DEBUG: {cls.DEBUG}")
        print(f"  Database: {cls.DATABASE_PATH}")
        print(f"  Tesseract: {cls.TESSERACT_PATH}")
        print(f"  Ollama: {cls.OLLAMA_HOST} ({cls.OLLAMA_MODEL})")
        print(f"  Gemini: {cls.GEMINI_MODEL} ({'configured' if cls.GEMINI_API_KEY else 'not configured'})")
        print(f"  Upload Folder: {cls.UPLOAD_FOLDER}")
        print(f"  Protocols: {cls.PROTOCOLS_FOLDER}")
        print("=" * 50)


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False


class TestingConfig(Config):
    """Testing configuration."""
    DEBUG = True
    DATABASE_NAME = 'test_svivy.db'
    DATABASE_PATH = os.path.join(Config.DATABASE_DIR, DATABASE_NAME)
    DATABASE_URL = f'sqlite:///{DATABASE_PATH}'


# Configuration mapping
config_map = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}

# Get configuration based on environment
env = os.environ.get('SVIVY_ENV', 'default')
config = config_map.get(env, DevelopmentConfig)

# Ensure folders exist
config.ensure_folders()


if __name__ == '__main__':
    # Print configuration for debugging
    config.print_config()

    # Validate
    issues = config.validate()
    if issues:
        print("\nConfiguration Issues:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("\nConfiguration is valid.")
