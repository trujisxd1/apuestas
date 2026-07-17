"""Motor de análisis: de-vig, probabilidad justa de consenso, EV, Kelly y detección de value.

Idea central (el método que usan los profesionales):
1. Cada casa publica cuotas con un margen (overround) a su favor.
2. Si juntamos MUCHAS casas y le quitamos el margen a cada una, el promedio de esas
   probabilidades "limpias" es la mejor estimación de la probabilidad REAL (el consenso).
3. Cuando UNA casa paga una cuota mayor a la que corresponde a esa probabilidad justa,
   ahí hay VALUE: nos están pagando de más. Eso es una apuesta +EV.
"""
from __future__ import annotations

from collections import defaultdict

from .models import Event, ValueBet


def implied_prob(decimal_odds: float) -> float:
    """Probabilidad implícita cruda de una cuota decimal (incluye margen de la casa)."""
    if decimal_odds <= 1.0:
        return 0.0
    return 1.0 / decimal_odds


def devig_book(outcomes: dict[str, float]) -> dict[str, float]:
    """Quita el margen de UNA casa normalizando las probabilidades para que sumen 1.

    outcomes: {selección: cuota_decimal}
    return:   {selección: probabilidad_justa} (suma 1.0)
    """
    raw = {name: implied_prob(price) for name, price in outcomes.items()}
    total = sum(raw.values())
    if total <= 0:
        return {name: 0.0 for name in outcomes}
    return {name: p / total for name, p in raw.items()}


def consensus_probabilities(event: Event, market: str = "h2h") -> dict[str, float]:
    """Probabilidad justa de consenso por selección, promediando las casas (ya sin margen)."""
    per_selection: dict[str, list[float]] = defaultdict(list)
    for bm in event.markets:
        if bm.market != market:
            continue
        book_odds = {o.name: o.price for o in bm.outcomes}
        for name, prob in devig_book(book_odds).items():
            per_selection[name].append(prob)

    if not per_selection:
        return {}

    avg = {name: sum(ps) / len(ps) for name, ps in per_selection.items()}
    # Renormaliza por si el promedio no suma exactamente 1.
    total = sum(avg.values())
    if total <= 0:
        return {}
    return {name: p / total for name, p in avg.items()}


def best_price_per_selection(event: Event, market: str = "h2h") -> dict[str, tuple[str, float]]:
    """Mejor cuota (la más alta) por selección y en qué casa está. {sel: (casa, cuota)}"""
    best: dict[str, tuple[str, float]] = {}
    for bm in event.markets:
        if bm.market != market:
            continue
        for o in bm.outcomes:
            if o.name not in best or o.price > best[o.name][1]:
                best[o.name] = (bm.bookmaker, o.price)
    return best


def expected_value(prob: float, decimal_odds: float) -> float:
    """EV por unidad apostada. Positivo = apuesta con value."""
    return prob * (decimal_odds - 1.0) - (1.0 - prob)


def kelly_stake(prob: float, decimal_odds: float, bankroll: float, fraction: float) -> float:
    """Monto a apostar según Kelly fraccionado. Nunca negativo."""
    b = decimal_odds - 1.0
    if b <= 0:
        return 0.0
    full_kelly = (b * prob - (1.0 - prob)) / b
    stake = bankroll * full_kelly * fraction
    return max(0.0, round(stake, 2))


def practical_stake(
    raw_stake: float,
    *,
    bankroll: float,
    min_stake: float,
    max_stake_pct: float,
    daily_cap: float | None = None,
) -> float:
    """Convierte el monto teórico de Kelly en un monto REAL y apostable en pesos:
    redondea a peso entero, respeta el mínimo de la casa y un tope de seguridad."""
    if raw_stake <= 0:
        return 0.0
    max_by_pct = bankroll * (max_stake_pct / 100.0)
    stake = max(min_stake, raw_stake)          # nunca menos del mínimo de la casa
    stake = min(stake, max_by_pct)             # nunca más del tope de seguridad
    if daily_cap is not None:
        stake = min(stake, daily_cap)
    return float(round(stake))                 # pesos enteros


def find_value_bets(
    events: list[Event],
    *,
    bankroll: float,
    kelly_fraction: float,
    min_edge_pct: float,
    market: str = "h2h",
    min_books: int = 2,
    min_stake: float = 10.0,
    max_stake_pct: float = 15.0,
    daily_cap: float | None = None,
) -> list[ValueBet]:
    """Recorre los eventos y devuelve las apuestas con value, ordenadas de mayor a menor edge."""
    results: list[ValueBet] = []

    for ev in events:
        fair = consensus_probabilities(ev, market)
        if not fair:
            continue
        n_books = sum(1 for bm in ev.markets if bm.market == market)
        if n_books < min_books:
            continue

        best = best_price_per_selection(ev, market)
        for selection, prob in fair.items():
            if selection not in best or prob <= 0:
                continue
            book, price = best[selection]
            edge = expected_value(prob, price)  # por unidad
            edge_pct = edge * 100.0
            if edge_pct < min_edge_pct:
                continue

            raw = kelly_stake(prob, price, bankroll, kelly_fraction)
            stake = practical_stake(
                raw, bankroll=bankroll, min_stake=min_stake,
                max_stake_pct=max_stake_pct, daily_cap=daily_cap,
            )

            results.append(
                ValueBet(
                    event=ev.label,
                    sport=ev.sport_title,
                    commence_time=ev.commence_time,
                    selection=selection,
                    best_bookmaker=book,
                    best_price=price,
                    fair_price=(1.0 / prob) if prob > 0 else 0.0,
                    fair_probability=prob,
                    edge_pct=edge_pct,
                    stake_suggestion=stake,
                    num_books=n_books,
                )
            )

    results.sort(key=lambda v: v.edge_pct, reverse=True)
    return results
