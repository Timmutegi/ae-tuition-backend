from pydantic_settings import BaseSettings
from typing import Optional, List
import os

class Settings(BaseSettings):
    # Application settings
    SECRET_KEY: str = "your-secret-key-here"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 9000

    # Environment setting (development/production)
    ENVIRONMENT: str = "development"

    # JWT settings
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    # Database settings
    POSTGRES_USER: str = "ae"
    POSTGRES_PASSWORD: str = "Passw0rd"
    POSTGRES_DB: str = "ae_tuition"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5440
    SQL_ECHO: bool = False  # Set to True for SQL query debugging

    # AWS settings
    AWS_ACCESS_KEY: Optional[str] = None
    AWS_SECRET_KEY: Optional[str] = None
    AWS_S3_BUCKET: Optional[str] = None
    AWS_REGION: str = "eu-west-2"

    # CloudFront settings
    CLOUDFRONT_URL: Optional[str] = None

    # Email settings
    RESEND_API_KEY: Optional[str] = None
    FROM_EMAIL: str = "smart-tutor@app.smart-tutorai.com"

    # OpenAI settings (for AI-generated distractors in MCQ tests)
    OPENAI_API_KEY: Optional[str] = None
    FRONTEND_URL: str = "http://localhost:4200"

    # Default admin settings
    DEFAULT_ADMIN_EMAIL: str = "support@ae-tuition.com"
    DEFAULT_ADMIN_USERNAME: str = "admin"
    DEFAULT_ADMIN_PASSWORD: str = "Admin123!!"
    DEFAULT_ADMIN_FULL_NAME: str = "Admin"

    # Security Settings (Production Only)
    REDIS_URL: str = "memory://"
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_AUTH: str = "5/minute"
    RATE_LIMIT_DEFAULT: str = "200/minute"
    IP_BLOCK_THRESHOLD: int = 10
    IP_BLOCK_DURATION_MINUTES: int = 60
    IP_TRACK_WINDOW_MINUTES: int = 5
    SECURITY_ALERT_EMAIL: str = "support@ae-tuition.com"
    TRUSTED_PROXIES: str = "127.0.0.1"

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def trusted_proxy_list(self) -> List[str]:
        return [p.strip() for p in self.TRUSTED_PROXIES.split(",")]

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()