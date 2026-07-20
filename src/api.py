"""API REST con FastAPI para consultar eventos y apuestas con value."""
from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import store
from .analysis import (
    build_legs,
    evaluate_parlay,
    find_value_bets,
    predict_all,
    suggest_parlay,
)
from .config import settings
from .models import (
    Event,
    Leg,
    MatchPrediction,
    ParlayEvaluation,
    ValueBet,
)
from .odds_client import OddsClient, POPULAR_SPORTS

app = FastAPI(
    title="Plataforma de Value Betting",
    description=(
        "Detecta apuestas con VALUE comparando el consenso del mercado (de-vig ponderado) "
        "contra la mejor cuota disponible, y estima quién puede ganar con nivel de confianza. "
        "No garantiza ganar — reduce el margen en tu contra y te da control."
    ),
    version="2.0.0",
)

client = OddsClient()
WEB_DIR = Path(__file__).resolve().parent.parent / "web"

store.init_db()


@app.get("/", include_in_schema=False)
def frontend():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/info")
def info():
    return {
        "app": "Value Betting Platform",
        "version": "2.0.0",
        "mode": "demo (sin API key)" if settings.demo_mode else "live",
        "bankroll": settings.bankroll,
        "daily_cap": settings.daily_cap,
        "network_blocked": client.fell_back,
        "network_detail": client.last_error,
        "sports": POPULAR_SPORTS,
        "cache": client.cache.stats(),
        "endpoints": [
            "/predictions", "/legs", "/value-bets", "/best", "/events",
            "/parlay/suggest", "/parlay/evaluate", "/bets", "/stats", "/usage",
        ],
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
    if settings.access_key and settings.access_key not in (k, x_access_key):
        raise HTTPException(status_code=401, detail="Clave de acceso requerida o inválida (usa ?k=...).")


# ------------------------------------------------------------------ lectura

@app.get("/events", response_model=list[Event], dependencies=[Depends(check_access)])
def events(sport: str = Query("ligamx", description="Liga: ligamx, epl, mlb, nba, nfl...")):
    try:
        return client.fetch_events(_sport_key(sport))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Error consultando cuotas: {exc}") from exc


@app.get("/predictions", response_model=list[MatchPrediction], dependencies=[Depends(check_access)])
def predictions(sport: str = Query("ligamx")):
    """Predicción de cada partido: quién puede ganar, con qué % y qué tan confiable es."""
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
    only_caliente: bool = Query(False, description="Solo value que EXISTE en Caliente"),
):
    evs = client.fetch_events(_sport_key(sport))
    return find_value_bets(
        evs,
        bankroll=settings.bankroll,
        kelly_fraction=settings.kelly_fraction,
        min_edge_pct=settings.min_edge if min_edge is None else min_edge,
        min_stake=settings.min_stake,
        max_stake_pct=settings.max_stake_pct,
        daily_cap=_remaining_daily_cap(),
        only_my_book=only_caliente,
    )


@app.get("/best", response_model=ValueBet | dict, dependencies=[Depends(check_access)])
def best(
    sport: str = Query("ligamx"),
    only_caliente: bool = Query(False),
):
    """La MEJOR apuesta (mayor value) del deporte pedido."""
    evs = client.fetch_events(_sport_key(sport))
    bets = find_value_bets(
        evs,
        bankroll=settings.bankroll,
        kelly_fraction=settings.kelly_fraction,
        min_edge_pct=settings.min_edge,
        min_stake=settings.min_stake,
        max_stake_pct=settings.max_stake_pct,
        daily_cap=_remaining_daily_cap(),
        only_my_book=only_caliente,
    )
    if not bets:
        return {"mensaje": "Hoy no hay ninguna apuesta con value suficiente. Lo mejor: no apostar."}
    return bets[0]


# ------------------------------------------------------------------ combinadas

@app.get("/parlay/suggest", response_model=ParlayEvaluation | dict, dependencies=[Depends(check_access)])
def parlay_suggest(
    sport: str = Query("ligamx"),
    size: int = Query(3, ge=2, le=5, description="Cuántas patas (2-5)"),
):
    """Arma automáticamente una combinada sensata: las patas más probables de
    partidos distintos, con el cálculo real de probabilidad y value."""
    evs = client.fetch_events(_sport_key(sport), markets="h2h,totals,btts")
    parlay = suggest_parlay(
        evs,
        bankroll=settings.bankroll,
        kelly_fraction=settings.kelly_fraction,
        min_stake=settings.min_stake,
        max_stake_pct=settings.max_stake_pct,
        size=size,
    )
    if parlay is None:
        return {"mensaje": "No hay suficientes patas confiables para armar una combinada hoy."}
    return parlay


class ParlayRequest(BaseModel):
    sport: str = "ligamx"
    legs: list[dict]  # cada uno: {event_id, selection} o el objeto Leg completo


@app.post("/parlay/evaluate", response_model=ParlayEvaluation, dependencies=[Depends(check_access)])
def parlay_evaluate(req: ParlayRequest):
    """Evalúa una combinada armada por el usuario. Recibe las patas elegidas
    (event_id + selection) y devuelve probabilidad conjunta, value y cuánto apostar."""
    evs = client.fetch_events(_sport_key(req.sport), markets="h2h,totals,btts")
    all_legs = {(l.event_id, l.selection): l for l in build_legs(evs)}

    chosen: list[Leg] = []
    for item in req.legs:
        key = (item.get("event_id"), item.get("selection"))
        lg = all_legs.get(key)
        if lg is not None:
            chosen.append(lg)

    if len(chosen) < 2:
        raise HTTPException(400, "Elige al menos 2 patas válidas para una combinada.")

    return evaluate_parlay(
        chosen,
        bankroll=settings.bankroll,
        kelly_fraction=settings.kelly_fraction,
        min_stake=settings.min_stake,
        max_stake_pct=settings.max_stake_pct,
    )


# ------------------------------------------------------------------ registro / bankroll

class NewBet(BaseModel):
    event: str
    selection: str
    odds: float = Field(gt=1.0)
    stake: float = Field(gt=0)
    market: str = "Resultado"
    bookmaker: str = "Caliente"
    probability: float | None = None
    is_parlay: bool = False
    notes: str | None = None


class SettleReq(BaseModel):
    status: str  # ganada | perdida | nula


def _remaining_daily_cap() -> float | None:
    """Cuánto queda del límite diario (None si no hay límite configurado)."""
    if settings.daily_cap <= 0:
        return None
    return max(0.0, settings.daily_cap - store.staked_today())


@app.get("/bets", dependencies=[Depends(check_access)])
def get_bets(limit: int = Query(100, ge=1, le=500)):
    return store.list_bets(limit)


@app.post("/bets", dependencies=[Depends(check_access)])
def create_bet(bet: NewBet):
    """Registra una apuesta que hiciste. Respeta el límite diario configurado."""
    remaining = _remaining_daily_cap()
    if remaining is not None and bet.stake > remaining + 1e-6:
        raise HTTPException(
            400,
            f"Te pasarías del límite diario. Hoy te quedan ${remaining:.0f} de "
            f"${settings.daily_cap:.0f}. Descansa o baja el monto.",
        )
    bet_id = store.add_bet(
        event=bet.event, selection=bet.selection, odds=bet.odds, stake=bet.stake,
        market=bet.market, bookmaker=bet.bookmaker, probability=bet.probability,
        is_parlay=bet.is_parlay, notes=bet.notes,
    )
    return {"id": bet_id, "ok": True, "restante_hoy": _remaining_daily_cap()}


@app.post("/bets/{bet_id}/settle", dependencies=[Depends(check_access)])
def settle(bet_id: int, req: SettleReq):
    """Marca el resultado de una apuesta (ganada/perdida/nula)."""
    try:
        ok = store.settle_bet(bet_id, req.status)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not ok:
        raise HTTPException(404, "No existe esa apuesta.")
    return {"ok": True, "stats": store.stats(settings.bankroll)}


@app.delete("/bets/{bet_id}", dependencies=[Depends(check_access)])
def remove_bet(bet_id: int):
    if not store.delete_bet(bet_id):
        raise HTTPException(404, "No existe esa apuesta.")
    return {"ok": True}


@app.get("/stats", dependencies=[Depends(check_access)])
def get_stats():
    """La verdad de cómo vas: neto, ROI, racha, acierto y calibración del motor."""
    s = store.stats(settings.bankroll)
    s["restante_hoy"] = _remaining_daily_cap()
    return s
