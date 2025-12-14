import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()


@dataclass
class Settings:
    # Frontend
    # frontend_origin: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")

    # Pinecone
    pinecone_api_key: str = os.getenv("PINECONE_API_KEY", "")
    pinecone_index: str = os.getenv("PINECONE_INDEX", "sira-vectors")

    # External Search Providers
    serpapi_key: str = os.getenv("SERPAPI_KEY", "")
    brave_key: str = os.getenv("BRAVE_KEY", "")

    # 🔵 Twitter / X API
    twitter_bearer_token: str = os.getenv("TWITTER_BEARER_TOKEN", "")

    # 🔵 OpenWeather API (NEW)
    openweather_api_key: str = os.getenv("OPENWEATHER_API_KEY", "")

    # OpenAI Summarizer
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    summarizer_model: str = os.getenv("SUMMARIZER_MODEL", "gpt-4.1-mini")

    # Supabase (Backend Only)
    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_service_role_key: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

    # SMTP / Email
    smtp_host: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    smtp_from_email: str = os.getenv("SMTP_FROM_EMAIL", "")
    smtp_from_name: str = os.getenv("SMTP_FROM_NAME", "SIRA")

    # App meta
    api_version: str = "0.1.0"


settings = Settings()
