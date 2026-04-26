import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / ".env")


def resolve_project_path(value: str) -> str:
    path = Path(value).expanduser()
    if path.is_absolute():
        return str(path)
    return str((PROJECT_ROOT / path).resolve())


def resolve_database_url(value: str) -> str:
    if not value.startswith("sqlite:///") or value == "sqlite:///:memory:":
        return value

    sqlite_path = Path(value.removeprefix("sqlite:///")).expanduser()
    if sqlite_path.is_absolute():
        return value
    return f"sqlite:///{(PROJECT_ROOT / sqlite_path).resolve()}"


class Config:
    MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o")

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

    DB_PATH = resolve_database_url(os.getenv("DB_PATH", "sqlite:///sqlite.db"))
    JOB_SEARCH_CONFIG_PATH = resolve_project_path(
        os.getenv("JOB_SEARCH_CONFIG_PATH", "config/job_search.yaml")
    )

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_DIR = resolve_project_path(os.getenv("LOG_DIR", "logs"))
    LOG_FILE = os.getenv("LOG_FILE", "daily_summary.log")
    LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", "1048576"))
    LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "5"))
    
    # Configuration LangSmith (Traçabilité et Debug)
    LANGCHAIN_TRACING = os.getenv("LANGCHAIN_TRACING", "false").lower() == "true"
    LANGCHAIN_API_KEY = os.getenv("LANGCHAIN_API_KEY")
    LANGCHAIN_PROJECT = os.getenv("LANGCHAIN_PROJECT", "job-scraper")
    
    # Configuration Email
    SMTP_USER = os.getenv("SMTP_USER", "bot@jobscraper.local")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    EMAIL_DELIVERY_MODE = os.getenv("EMAIL_DELIVERY_MODE", "mock").lower()

    # Configuration Serper.dev pour la découverte automatique de sources.
    SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
    SERPER_SEARCH_URL = os.getenv("SERPER_SEARCH_URL", "https://google.serper.dev/search")
    SERPER_RESULTS_PER_QUERY = int(os.getenv("SERPER_RESULTS_PER_QUERY", "10"))
    
    # Email destinataire par défaut
    RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL", "maximekets80@gmail.com")

settings = Config()
