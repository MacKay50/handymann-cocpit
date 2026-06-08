import os
import pathlib
from dotenv import load_dotenv

load_dotenv()

# Default: haandvaerker.db sits next to pyproject.toml (project root), not CWD.
# This makes the path stable regardless of which directory uvicorn is launched from.
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
_DEFAULT_DB = f"sqlite:///{_PROJECT_ROOT / 'haandvaerker.db'}"

DATABASE_URL: str = os.getenv("DATABASE_URL", _DEFAULT_DB)
ENV: str = os.getenv("ENV", "development")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

# Email / IMAP (optional — leave blank to disable email polling)
EMAIL_IMAP_HOST: str = os.getenv("EMAIL_IMAP_HOST", "")
EMAIL_IMAP_PORT: int = int(os.getenv("EMAIL_IMAP_PORT", "993"))
EMAIL_USER: str = os.getenv("EMAIL_USER", "")
EMAIL_PASSWORD: str = os.getenv("EMAIL_PASSWORD", "")
EMAIL_FOLDER: str = os.getenv("EMAIL_FOLDER", "INBOX")

# Email / SMTP (optional — for sending reminders to customers)
SMTP_HOST: str = os.getenv("SMTP_HOST", "")
SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER: str = os.getenv("SMTP_USER", EMAIL_USER)      # reuse IMAP user if same account
SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", EMAIL_PASSWORD)
SMTP_FROM: str = os.getenv("SMTP_FROM", EMAIL_USER)
SMTP_USE_TLS: bool = os.getenv("SMTP_USE_TLS", "true").lower() == "true"

# Invoice reminder fees (øre, 0 = no fee)
REMINDER_FEE_ORE_1: int = int(os.getenv("REMINDER_FEE_ORE_1", "0"))   # 1st reminder
REMINDER_FEE_ORE_2: int = int(os.getenv("REMINDER_FEE_ORE_2", "10000"))  # 2nd: 100 kr
REMINDER_FEE_ORE_3: int = int(os.getenv("REMINDER_FEE_ORE_3", "25000"))  # Final: 250 kr

# Session signing (itsdangerous URLSafeSerializer)
SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-change-in-production")

# Local AI (optional — Ollama: http://localhost:11434, LM Studio: http://localhost:1234)
LOCAL_AI_ENDPOINT: str = os.getenv("LOCAL_AI_ENDPOINT", "")
LOCAL_AI_MODEL: str = os.getenv("LOCAL_AI_MODEL", "mistral")
# Fallback model tried if the primary model fails or times out (leave blank to disable)
LOCAL_AI_FALLBACK_MODEL: str = os.getenv("LOCAL_AI_FALLBACK_MODEL", "")


class _Settings:
    @property
    def secret_key(self) -> str:
        return SECRET_KEY

    @property
    def local_ai_endpoint(self) -> str:
        return LOCAL_AI_ENDPOINT

    @property
    def local_ai_model(self) -> str:
        return LOCAL_AI_MODEL

    @property
    def local_ai_fallback_model(self) -> str:
        return LOCAL_AI_FALLBACK_MODEL


settings = _Settings()
