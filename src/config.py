"""Configuración cargada desde variables de entorno / archivo .env."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    odds_api_key: str = ""
    odds_regions: str = "us,eu"
    odds_format: str = "decimal"
    kelly_fraction: float = 0.25
    bankroll: float = 100.0
    min_edge: float = 2.0
    # Apuesta mínima real (lo que acepta la casa; Caliente ~10 pesos).
    min_stake: float = 10.0
    # Tope de seguridad: nunca apostar más de este % del bankroll en una jugada.
    max_stake_pct: float = 15.0
    # Límite de gasto diario (pesos). El registro no te deja pasarte. 0 = sin límite.
    daily_cap: float = 40.0
    # Cuánto tiempo (segundos) se guardan las cuotas en caché para no quemar la cuota
    # de la API gratuita (500 consultas/mes). 600 = 10 minutos.
    cache_ttl: float = 600.0
    # Clave de acceso opcional (para que nadie te queme la cuota de la API).
    # Vacía = acceso libre. Si la pones, hay que abrir la app con ?k=TU_CLAVE
    access_key: str = ""

    base_url: str = "https://api.the-odds-api.com/v4"

    @property
    def demo_mode(self) -> bool:
        """Sin API key => corremos con datos de ejemplo."""
        return not self.odds_api_key.strip()


settings = Settings()
