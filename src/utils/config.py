"""
Configuration management for the invoice processing system
"""
from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    """Application settings"""

    # Google Cloud Configuration
    GCP_PROJECT_ID: str = "invoiceprocessingai2498"
    GCP_LOCATION: str = "us"
    GCP_PROCESSOR_ID: str = "cca0593594bfdba1"
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None

    # Database Configuration
    DATABASE_URL: str = "sqlite:///./invoice_processing.db"

    # API Configuration
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    DEBUG: bool = True

    # ML Model Configuration
    MODEL_PATH: str = "data/models/document_classifier.pkl"
    MIN_CONFIDENCE_THRESHOLD: float = 0.7

    # File Upload Configuration
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB
    ALLOWED_EXTENSIONS: list = [".pdf", ".png", ".jpg", ".jpeg"]
    UPLOAD_DIR: str = "uploads"

    class Config:
        env_file = ".env"
        case_sensitive = True


# Global settings instance
_settings = None


def get_settings() -> Settings:
    """Get application settings singleton"""
    global _settings
    if _settings is None:
        _settings = Settings()
        # Manually set environment variable if specified in settings
        if _settings.GOOGLE_APPLICATION_CREDENTIALS and not os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'):
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = _settings.GOOGLE_APPLICATION_CREDENTIALS
    return _settings