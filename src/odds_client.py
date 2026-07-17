"""Cliente de The Odds API con modo demo (datos de ejemplo) cuando no hay API key.

Docs de la API: https://the-odds-api.com/liveapi/guides/v4/
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from .config import settings
from .models import Event, BookmakerMarket, Outcome

# Ligas útiles para el usuario (claves de The Odds API).
POPULAR_SPORTS = {
    "ligamx": "soccer_mexico_ligamx",
    "epl": "soccer_epl",
    "laliga": "soccer_spain_la_liga",
    "champions": "soccer_uefa_champs_league",
    "mlb": "baseball_mlb",
    "nba": "basketball_nba",
    "nfl": "americanfootball_nfl",
}


class OddsClient:
    def __init__(self) -> None:
        self.key = settings.odds_api_key
        self.base = settings.base_url
        self.regions = settings.odds_regions
        self.fmt = settings.odds_format
        # Estado del último intento de red (para avisar al front si la red bloquea la API).
        self.last_error: str | None = None
        self.fell_back: bool = False

    # ---------- API real ----------
    def _parse_event(self, raw: dict) -> Event:
        markets: list[BookmakerMarket] = []
        for bm in raw.get("bookmakers", []):
            title = bm.get("title", bm.get("key", "?"))
            for mk in bm.get("markets", []):
                outcomes = []
                for o in mk.get("outcomes", []):
                    name = o["name"]
                    # En totals/spreads la línea (2.5, etc.) viene aparte: la doblamos en el nombre.
                    if o.get("point") is not None:
                        name = f"{name} {o['point']}"
                    outcomes.append(Outcome(name=name, price=float(o["price"])))
                if outcomes:
                    markets.append(
                        BookmakerMarket(bookmaker=title, market=mk["key"], outcomes=outcomes)
                    )
        return Event(
            id=raw["id"],
            sport_key=raw["sport_key"],
            sport_title=raw.get("sport_title", raw["sport_key"]),
            commence_time=datetime.fromisoformat(raw["commence_time"].replace("Z", "+00:00")),
            home_team=raw.get("home_team", "Local"),
            away_team=raw.get("away_team", "Visitante"),
            markets=markets,
        )

    def fetch_events(self, sport_key: str, markets: str = "h2h") -> list[Event]:
        """Trae eventos con cuotas reales. Sin key -> demo. Si la red bloquea la API,
        cae a demo (etiquetado) en vez de tronar."""
        self.last_error = None
        self.fell_back = False
        if settings.demo_mode:
            return demo_events(sport_key)

        url = f"{self.base}/sports/{sport_key}/odds"

        def _call(mkts: str):
            params = {
                "apiKey": self.key,
                "regions": self.regions,
                "markets": mkts,
                "oddsFormat": self.fmt,
            }
            with httpx.Client(timeout=20.0) as client:
                resp = client.get(url, params=params)
                resp.raise_for_status()
                return resp.json()

        try:
            try:
                data = _call(markets)
            except httpx.HTTPStatusError:
                # Algún mercado (ej. btts) puede no existir para este deporte: reintenta con h2h.
                if markets != "h2h":
                    data = _call("h2h")
                else:
                    raise
            return [self._parse_event(e) for e in data]
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            # Red corporativa bloqueando el host, o API caída: degradar a demo con aviso.
            self.last_error = str(exc)
            self.fell_back = True
            return demo_events(sport_key)

    def usage(self) -> dict:
        """Cuántas requests te quedan (viene en los headers de la última llamada)."""
        if settings.demo_mode:
            return {"mode": "demo", "remaining": "∞ (sin límite en demo)"}
        url = f"{self.base}/sports"
        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.get(url, params={"apiKey": self.key})
                resp.raise_for_status()
                return {
                    "mode": "live",
                    "remaining": resp.headers.get("x-requests-remaining", "?"),
                    "used": resp.headers.get("x-requests-used", "?"),
                }
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            return {
                "mode": "live (sin acceso)",
                "error": "La red bloquea la API o está caída. Prueba desde otra red (casa/hotspot).",
                "detail": str(exc),
            }


# ---------- Datos DEMO (para probar la plataforma sin API key) ----------
def _soon(hours: int) -> datetime:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).replace(microsecond=0)


def demo_events(sport_key: str = "soccer_mexico_ligamx") -> list[Event]:
    """Eventos de ejemplo con varias casas. Uno de ellos tiene value a propósito
    para que veas cómo el motor lo detecta."""

    def mk(book: str, home: float, draw: float, away: float, home_t: str, away_t: str):
        return BookmakerMarket(
            bookmaker=book,
            market="h2h",
            outcomes=[
                Outcome(name=home_t, price=home),
                Outcome(name="Draw", price=draw),
                Outcome(name=away_t, price=away),
            ],
        )

    def totals(book: str, over: float, under: float):
        return BookmakerMarket(
            bookmaker=book, market="totals",
            outcomes=[Outcome(name="Over 2.5", price=over), Outcome(name="Under 2.5", price=under)],
        )

    def btts(book: str, yes: float, no: float):
        return BookmakerMarket(
            bookmaker=book, market="btts",
            outcomes=[Outcome(name="Yes", price=yes), Outcome(name="No", price=no)],
        )

    # Partido 1: mercado parejo, SIN value real (todas las casas coinciden).
    ev1 = Event(
        id="demo-juarez-puebla",
        sport_key=sport_key,
        sport_title="Liga MX (DEMO)",
        commence_time=_soon(5),
        home_team="FC Juárez",
        away_team="Puebla",
        markets=[
            mk("Bet365", 1.90, 3.40, 4.20, "FC Juárez", "Puebla"),
            mk("Pinnacle", 1.92, 3.35, 4.10, "FC Juárez", "Puebla"),
            mk("DraftKings", 1.88, 3.45, 4.25, "FC Juárez", "Puebla"),
            mk("Caliente", 1.89, 3.30, 4.15, "FC Juárez", "Puebla"),
            totals("Bet365", 2.05, 1.75), totals("Pinnacle", 2.08, 1.73),
            totals("Caliente", 2.00, 1.80),
            btts("Bet365", 1.95, 1.85), btts("Caliente", 1.90, 1.90),
        ],
    )

    # Partido 2: una casa ("Caliente") paga DE MÁS al empate -> VALUE detectable.
    ev2 = Event(
        id="demo-leon-atlas",
        sport_key=sport_key,
        sport_title="Liga MX (DEMO)",
        commence_time=_soon(7),
        home_team="León",
        away_team="Atlas",
        markets=[
            mk("Bet365", 1.85, 3.50, 4.60, "León", "Atlas"),
            mk("Pinnacle", 1.83, 3.55, 4.70, "León", "Atlas"),
            mk("DraftKings", 1.86, 3.60, 4.50, "León", "Atlas"),
            mk("Caliente", 1.80, 4.30, 4.40, "León", "Atlas"),  # empate inflado
            totals("Bet365", 1.90, 1.90), totals("Pinnacle", 1.88, 1.92),
            totals("Caliente", 1.85, 1.95),
            btts("Bet365", 1.80, 2.00), btts("Caliente", 1.75, 2.05),
        ],
    )

    return [ev1, ev2]
