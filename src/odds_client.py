"""Cliente de The Odds API con modo demo (datos de ejemplo) cuando no hay API key.

Docs de la API: https://the-odds-api.com/liveapi/guides/v4/
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from .cache import TTLCache
from .config import settings
from .models import Event, BookmakerMarket, Outcome

# Ligas/deportes útiles para el usuario (claves de The Odds API).
POPULAR_SPORTS = {
    # Fútbol
    "ligamx": "soccer_mexico_ligamx",
    "epl": "soccer_epl",
    "laliga": "soccer_spain_la_liga",
    "seriea": "soccer_italy_serie_a",
    "bundesliga": "soccer_germany_bundesliga",
    "ligue1": "soccer_france_ligue_one",
    "mls": "soccer_usa_mls",
    "champions": "soccer_uefa_champs_league",
    "libertadores": "soccer_conmebol_copa_libertadores",
    # EE.UU.
    "nba": "basketball_nba",
    "nfl": "americanfootball_nfl",
    "mlb": "baseball_mlb",
    "nhl": "icehockey_nhl",
    "ncaab": "basketball_ncaab",
    # Combate
    "ufc": "mma_mixed_martial_arts",
    "boxeo": "boxing_boxing",
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
        # Caché para no quemar la cuota de la API (las cuotas no cambian cada segundo).
        self.cache = TTLCache(ttl_seconds=settings.cache_ttl)

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
        """Trae eventos con cuotas reales (con caché). Sin key -> demo. Si la red bloquea
        la API, cae a demo (etiquetado) en vez de tronar."""
        self.last_error = None
        self.fell_back = False
        if settings.demo_mode:
            return demo_events(sport_key)

        cache_key = f"{sport_key}:{markets}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        events = self._fetch_live(sport_key, markets)
        # Solo cacheamos respuestas reales (no el fallback demo por red bloqueada).
        if events and not self.fell_back:
            self.cache.set(cache_key, events)
        return events

    def _fetch_live(self, sport_key: str, markets: str) -> list[Event]:
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

    # Partido 1: mercado parejo, casas coinciden (alto acuerdo, dato confiable).
    ev1 = Event(
        id="demo-juarez-puebla",
        sport_key=sport_key,
        sport_title="Liga MX (DEMO)",
        commence_time=_soon(5),
        home_team="FC Juárez",
        away_team="Puebla",
        markets=[
            mk("Pinnacle", 1.92, 3.35, 4.10, "FC Juárez", "Puebla"),
            mk("Bet365", 1.90, 3.40, 4.20, "FC Juárez", "Puebla"),
            mk("DraftKings", 1.88, 3.45, 4.25, "FC Juárez", "Puebla"),
            mk("William Hill", 1.91, 3.38, 4.15, "FC Juárez", "Puebla"),
            mk("Caliente", 1.89, 3.30, 4.15, "FC Juárez", "Puebla"),
            totals("Bet365", 2.05, 1.75), totals("Pinnacle", 2.08, 1.73),
            totals("Caliente", 2.00, 1.80),
            btts("Bet365", 1.95, 1.85), btts("Caliente", 1.90, 1.90),
        ],
    )

    # Partido 2: Caliente paga DE MÁS al empate -> VALUE detectable EN TU CASA.
    ev2 = Event(
        id="demo-leon-atlas",
        sport_key=sport_key,
        sport_title="Liga MX (DEMO)",
        commence_time=_soon(7),
        home_team="León",
        away_team="Atlas",
        markets=[
            mk("Pinnacle", 1.83, 3.55, 4.70, "León", "Atlas"),
            mk("Bet365", 1.85, 3.50, 4.60, "León", "Atlas"),
            mk("DraftKings", 1.86, 3.60, 4.50, "León", "Atlas"),
            mk("William Hill", 1.84, 3.52, 4.65, "León", "Atlas"),
            mk("Caliente", 1.95, 3.55, 4.40, "León", "Atlas"),  # local inflado -> value en Caliente
            totals("Bet365", 1.90, 1.90), totals("Pinnacle", 1.88, 1.92),
            totals("Caliente", 1.85, 1.95),
            btts("Bet365", 1.80, 2.00), btts("Caliente", 1.75, 2.05),
        ],
    )

    # Partido 3: favorito FUERTE y claro (alta confianza, buena pata para combinada).
    ev3 = Event(
        id="demo-america-queretaro",
        sport_key=sport_key,
        sport_title="Liga MX (DEMO)",
        commence_time=_soon(9),
        home_team="América",
        away_team="Querétaro",
        markets=[
            mk("Pinnacle", 1.26, 6.00, 11.0, "América", "Querétaro"),
            mk("Bet365", 1.25, 6.25, 12.0, "América", "Querétaro"),
            mk("DraftKings", 1.27, 5.80, 10.5, "América", "Querétaro"),
            mk("William Hill", 1.26, 6.10, 11.5, "América", "Querétaro"),
            mk("Caliente", 1.28, 5.75, 10.0, "América", "Querétaro"),
            totals("Bet365", 1.75, 2.05), totals("Pinnacle", 1.73, 2.08),
            totals("Caliente", 1.70, 2.10),
            btts("Bet365", 2.00, 1.80), btts("Caliente", 2.05, 1.75),
        ],
    )

    # Partido 4: casas MUY discordantes (bajo acuerdo -> dato poco confiable, se avisa).
    ev4 = Event(
        id="demo-tigres-chivas",
        sport_key=sport_key,
        sport_title="Liga MX (DEMO)",
        commence_time=_soon(11),
        home_team="Tigres",
        away_team="Chivas",
        markets=[
            mk("Pinnacle", 2.10, 3.30, 3.40, "Tigres", "Chivas"),
            mk("Bet365", 1.75, 3.60, 4.50, "Tigres", "Chivas"),  # muy distinto de Pinnacle
            mk("DraftKings", 2.40, 3.10, 3.00, "Tigres", "Chivas"),
            mk("Caliente", 1.95, 3.40, 3.90, "Tigres", "Chivas"),
        ],
    )

    return [ev3, ev1, ev2, ev4]
