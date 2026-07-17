"""Tipos de datos de la plataforma."""
from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class Outcome(BaseModel):
    """Una selección concreta (ej. 'Cruz Azul' a cuota 2.10) en una casa."""
    name: str
    price: float  # cuota decimal


class BookmakerMarket(BaseModel):
    """Las cuotas de un mercado (ej. h2h) en UNA casa de apuestas."""
    bookmaker: str
    market: str  # "h2h", "totals", etc.
    outcomes: list[Outcome]


class Event(BaseModel):
    """Un partido/evento con las cuotas de todas las casas disponibles."""
    id: str
    sport_key: str
    sport_title: str
    commence_time: datetime
    home_team: str
    away_team: str
    markets: list[BookmakerMarket] = Field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{self.home_team} vs {self.away_team}"


class OutcomeProb(BaseModel):
    """Probabilidad de un resultado concreto (ej. 'León' 54%)."""
    name: str
    probability: float       # 0-1
    fair_odds: float         # cuota justa = 1/probabilidad


class MatchPrediction(BaseModel):
    """Predicción de un partido: quién es más probable que gane y con qué probabilidad."""
    event: str
    sport: str
    commence_time: datetime
    outcomes: list[OutcomeProb]   # ordenados de mayor a menor probabilidad
    favorite: str
    favorite_probability: float
    confidence: str               # etiqueta: favorito fuerte / parejo / etc.
    analysis: str                 # explicación en texto
    num_books: int
    value_note: str | None = None # aviso si además hay value


class ValueBet(BaseModel):
    """Una apuesta con value detectado por el motor."""
    event: str
    sport: str
    commence_time: datetime
    selection: str
    best_bookmaker: str
    best_price: float          # la mejor cuota encontrada
    fair_price: float          # cuota justa según el consenso (sin margen)
    fair_probability: float    # probabilidad justa del consenso (0-1)
    edge_pct: float            # ventaja/value en %
    stake_suggestion: float    # cuánto apostar (Kelly fraccionado, con topes)
    num_books: int             # cuántas casas se usaron para el consenso

    def summary(self) -> str:
        return (
            f"{self.event}  [{self.sport}]\n"
            f"  → Apuesta: {self.selection} @ {self.best_price:.2f} ({self.best_bookmaker})\n"
            f"  → Cuota justa: {self.fair_price:.2f}  |  Prob. justa: {self.fair_probability*100:.1f}%\n"
            f"  → VALUE: +{self.edge_pct:.1f}%  |  Apostar: ${self.stake_suggestion:.2f}  "
            f"({self.num_books} casas)"
        )
