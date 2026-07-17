"""API REST con FastAPI para consultar eventos y apuestas con value."""
from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse

from .analysis import build_legs, find_value_bets, predict_all, predict_match
from .config import settings
from .models import Event, Leg, MatchPrediction, ValueBet
from .odds_client import OddsClient, POPULAR_SPORTS

app = FastAPI(
    title="Plataforma de Value Betting",
    description=(
        "Detecta apuestas con VALUE comparando el consenso del mercado (de-vig) "
        "contra la mejor cuota disponible. No garantiza ganar — reduce el margen en tu contra."
    ),
    version="1.0.0",
)

client = OddsClient()
WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@app.get("/", include_in_schema=False)
def frontend():
    """Sirve el panel web."""
    return FileResponse(WEB_DIR / "index.html")


@app.get("/info")
def info():
    return {
        "app": "Value Betting Platform",
        "mode": "demo (sin API key)" if settings.demo_mode else "live",
        "bankroll": settings.bankroll,
        "network_blocked": client.fell_back,
        "network_detail": client.last_error,
        "sports": POPULAR_SPORTS,
        "endpoints": ["/events", "/value-bets", "/best", "/usage"],
        "nota": "Apostar es entretenimiento, no una inversión. La casa siempre tiene ventaja.",
    }


@app.get("/usage")
def usage():
    return client.usage()


def _sport_key(sport: str) -> str:
    return POPULAR_SPORTS.get(sport, sport)


def check_access(
    k: str | None = Query(None, description="Clave de acceso (si está configurada)"),
    x_access_key: str | None = Header(None),
) -> None:
    """Si hay ACCESS_KEY configurada, exige ?k=... o header x-access-key correcto."""
    if settings.access_key and settings.access_key not in (k, x_access_key):
        raise HTTPException(status_code=401, detail="Clave de acceso requerida o inválida (usa ?k=...).")


@app.get("/events", response_model=list[Event], dependencies=[Depends(check_access)])
def events(sport: str = Query("ligamx", description="Liga: ligamx, epl, mlb, nba, nfl...")):
    try:
        return client.fetch_events(_sport_key(sport))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Error consultando cuotas: {exc}") from exc


@app.get("/predictions", response_model=list[MatchPrediction], dependencies=[Depends(check_access)])
def predictions(sport: str = Query("ligamx")):
    """Predicción de cada partido: quién es más probable que gane y con qué %."""
    evs = client.fetch_events(_sport_key(sport))
    return predict_all(evs)


@app.get("/legs", response_model=list[Leg], dependencies=[Depends(check_access)])
def legs(sport: str = Query("ligamx")):
    """Patas seleccionables (resultado, goles, ambos anotan) para armar combinadas."""
    evs = client.fetch_events(_sport_key(sport), markets="h2h,totals,btts")
    return build_legs(evs)


@app.get("/value-bets", response_model=list[ValueBet], dependencies=[Depends(check_access)])
def value_bets(
    sport: str = Query("ligamx"),
    min_edge: float | None = Query(None, description="Value mínimo en %. Default: el del .env"),
):
    evs = client.fetch_events(_sport_key(sport))
    return find_value_bets(
        evs,
        bankroll=settings.bankroll,
        kelly_fraction=settings.kelly_fraction,
        min_edge_pct=settings.min_edge if min_edge is None else min_edge,
        min_stake=settings.min_stake,
        max_stake_pct=settings.max_stake_pct,
        daily_cap=None,
    )


@app.get("/best", response_model=ValueBet | dict, dependencies=[Depends(check_access)])
def best(sport: str = Query("ligamx")):
    """La MEJOR apuesta (mayor value) del deporte pedido."""
    evs = client.fetch_events(_sport_key(sport))
    bets = find_value_bets(
        evs,
        bankroll=settings.bankroll,
        kelly_fraction=settings.kelly_fraction,
        min_edge_pct=settings.min_edge,
        min_stake=settings.min_stake,
        max_stake_pct=settings.max_stake_pct,
    )
    if not bets:
        return {"mensaje": "Hoy no hay ninguna apuesta con value suficiente. Lo mejor: no apostar."}
    return bets[0]
