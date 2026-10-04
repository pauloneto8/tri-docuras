from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_SECRET = "change-me-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "assistfin"
    database_url: str = "postgresql://app2:app2@app2-db:5432/app2"
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    anthropic_api_key: str = ""
    anthropic_model_fast: str = "claude-haiku-4-5"
    anthropic_model_reasoning: str = "claude-sonnet-5"
    enable_ai_insights: bool = False
    enable_ai_nlu_fallback: bool = False
    enable_ai_orchestrator: bool = False
    enable_agent_v2: bool = False
    agent_v2_users: str = ""
    port: int = 8000
    secret_key: str = _INSECURE_SECRET
    allow_registration: bool = True
    root_emails: str = "pauloneto8@gmail.com"
    trusted_hosts: str = "localhost,127.0.0.1"
    app_timezone: str = "America/Recife"
    debug: bool = False
    backup_dir: str = "/app/data/backups"
    backup_keep: int = 20
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_verify_token: str = ""
    whatsapp_app_secret: str = ""

    @field_validator("secret_key")
    @classmethod
    def secret_key_must_be_set(cls, value: str) -> str:
        if not value or value == _INSECURE_SECRET:
            raise ValueError(
                "SECRET_KEY deve ser definida via variável de ambiente (valor forte e único)."
            )
        return value

    @property
    def root_email_set(self) -> set[str]:
        return {email.strip().lower() for email in self.root_emails.split(",") if email.strip()}

    @property
    def trusted_host_list(self) -> list[str]:
        return [host.strip() for host in self.trusted_hosts.split(",") if host.strip()]

    @property
    def agent_v2_user_set(self) -> set[int]:
        ids: set[int] = set()
        for part in (self.agent_v2_users or "").split(","):
            part = part.strip()
            if not part:
                continue
            try:
                ids.add(int(part))
            except ValueError:
                continue
        return ids


settings = Settings()
