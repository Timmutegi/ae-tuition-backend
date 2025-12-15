from pydantic_settings import BaseSettings
from typing import Optional
import os

class Settings(BaseSettings):
    # Application settings
    SECRET_KEY: str = "your-secret-key-here"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 9000

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
    FRONTEND_URL: str = "http://localhost:4200"

    # Default admin settings
    DEFAULT_ADMIN_EMAIL: str = "support@ae-tuition.com"
    DEFAULT_ADMIN_USERNAME: str = "admin"
    DEFAULT_ADMIN_PASSWORD: str = "Admin123!!"
    DEFAULT_ADMIN_FULL_NAME: str = "Admin"

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()