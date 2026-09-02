from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# O .env fica na RAIZ do repositório (um nível acima de backend/), o mesmo que o
# docker-compose lê para subir o banco - uma fonte de verdade só para os segredos.
ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    database_url: str

    # 32 bytes em hexadecimal. Cifra as chaves de IA guardadas no banco; a chave
    # da IA nunca mora no ambiente (ver planos/plano_v4_1..., §1.1).
    ai_master_encryption_key: str = ""

    # Assina o cookie de sessão. Trocar esta chave desloga todo mundo.
    session_secret_key: str

    # Cifra dado pessoal no banco (CPF). 32 bytes em hexadecimal.
    data_encryption_key: str = ""

    # SMTP do código de login. Vazio = código vai para o log, não para o e-mail.
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
