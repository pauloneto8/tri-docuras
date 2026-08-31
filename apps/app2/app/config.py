from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_SECRET = "change-me-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "assistfin"
    database_url: str = "postgresql://app2:app2@app2-db:5432/app2"
    ollama_url: str = "http://ollama:11434"
    ollama_model: str = "qwen3:1.7b"
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    port: int = 8000
    secret_key: str = _INSECURE_SECRET
    allow_registration: bool = True
    root_emails: str = "pauloneto8@gmail.com"
    trusted_hosts: str = "localhost,127.0.0.1"
    app_timezone: str = "America/Recife"
    debug: bool = False

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


settings = Settings()
